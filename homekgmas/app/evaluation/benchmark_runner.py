"""Benchmark helpers for comparing orchestration strategies."""

from __future__ import annotations

from statistics import mean
from typing import List

from pydantic import BaseModel, Field

from app.api.schemas import TaskRequest
from app.evaluation.baselines import build_keyword_baseline_plan
from app.environment.simulator import HomeSimulator
from app.orchestrator.central_node import CentralNode


class BenchmarkRecord(BaseModel):
    """Stores one benchmark comparison row."""

    task_id: str
    task_description: str
    mas_action_count: int
    baseline_action_count: int
    mas_conflict_count: int
    mas_selected_agents: List[str] = Field(default_factory=list)
    mas_success: bool = True


class BenchmarkSummary(BaseModel):
    """Aggregate statistics over a benchmark run."""

    task_count: int
    mas_avg_action_count: float
    baseline_avg_action_count: float
    mas_avg_conflict_count: float
    mas_success_rate: float


class BenchmarkReport(BaseModel):
    """Full benchmark report."""

    records: List[BenchmarkRecord] = Field(default_factory=list)
    summary: BenchmarkSummary


class BenchmarkRunner:
    """Runs the current MAS against a simple baseline."""

    def __init__(self, central_node: CentralNode, simulator: HomeSimulator) -> None:
        self.central_node = central_node
        self.simulator = simulator

    def run(self, tasks: List[TaskRequest]) -> BenchmarkReport:
        records = []
        for task in tasks:
            result = self.central_node.handle_task(task)
            baseline_plan = build_keyword_baseline_plan(
                task.task_id,
                task.description,
                self.simulator.get_home_state(),
            )
            records.append(
                BenchmarkRecord(
                    task_id=task.task_id,
                    task_description=task.description,
                    mas_action_count=len(result.plan.selected_actions),
                    baseline_action_count=len(baseline_plan.selected_actions),
                    mas_conflict_count=len(result.conflicts),
                    mas_selected_agents=result.selected_agents,
                    mas_success=result.execution.success,
                )
            )

        if records:
            summary = BenchmarkSummary(
                task_count=len(records),
                mas_avg_action_count=mean(record.mas_action_count for record in records),
                baseline_avg_action_count=mean(record.baseline_action_count for record in records),
                mas_avg_conflict_count=mean(record.mas_conflict_count for record in records),
                mas_success_rate=sum(1 for record in records if record.mas_success) / len(records),
            )
        else:
            summary = BenchmarkSummary(
                task_count=0,
                mas_avg_action_count=0.0,
                baseline_avg_action_count=0.0,
                mas_avg_conflict_count=0.0,
                mas_success_rate=0.0,
            )

        return BenchmarkReport(records=records, summary=summary)
