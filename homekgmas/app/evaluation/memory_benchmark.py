"""Benchmark helpers focused on memory-backend ablations within one framework family."""

from __future__ import annotations

from statistics import mean
from time import perf_counter

from pydantic import BaseModel, Field

from app.api.schemas import TaskRequest
from app.orchestrator.central_node import CentralNode


class MemoryBenchmarkRecord(BaseModel):
    """Per-task comparison row for one memory backend."""

    backend: str
    task_id: str
    task_description: str
    selected_agents: list[str] = Field(default_factory=list)
    retrieval_latency_ms: float = 0.0
    prompt_char_count: int = 0
    graph_fact_count: int = 0
    workspace_snippet_count: int = 0
    selected_action_count: int = 0
    conflict_count: int = 0
    success: bool = True


class MemoryBenchmarkSummary(BaseModel):
    """Aggregate statistics for one backend."""

    backend: str
    task_count: int
    avg_retrieval_latency_ms: float
    avg_prompt_char_count: float
    avg_graph_fact_count: float
    avg_workspace_snippet_count: float
    avg_selected_action_count: float
    avg_conflict_count: float
    success_rate: float


class MemoryBenchmarkReport(BaseModel):
    """Full comparison report across backends."""

    records: list[MemoryBenchmarkRecord] = Field(default_factory=list)
    summaries: list[MemoryBenchmarkSummary] = Field(default_factory=list)


class MemoryBenchmarkRunner:
    """Run the same task set across multiple memory backends."""

    def __init__(self, central_nodes: dict[str, CentralNode]) -> None:
        self.central_nodes = central_nodes

    def run(self, tasks: list[TaskRequest]) -> MemoryBenchmarkReport:
        records: list[MemoryBenchmarkRecord] = []

        for backend, central_node in self.central_nodes.items():
            for task in tasks:
                home_state = central_node.simulator.get_home_state()
                selected_agents = central_node.wakeup_manager.select_agents(
                    task,
                    central_node.agent_registry,
                )
                start = perf_counter()
                bundles = {
                    agent.name: central_node.memory_coordinator.retrieve_for_agent_with_context(
                        agent.name,
                        task.description,
                        sensor_context=home_state.sensors.model_dump(mode="json"),
                    )
                    for agent in selected_agents
                }
                retrieval_latency_ms = round((perf_counter() - start) * 1000.0, 3)
                result = central_node.handle_task(task)
                records.append(
                    MemoryBenchmarkRecord(
                        backend=backend,
                        task_id=task.task_id,
                        task_description=task.description,
                        selected_agents=[agent.name for agent in selected_agents],
                        retrieval_latency_ms=retrieval_latency_ms,
                        prompt_char_count=sum(bundle.prompt_char_count() for bundle in bundles.values()),
                        graph_fact_count=sum(len(bundle.graph_context.facts) for bundle in bundles.values()),
                        workspace_snippet_count=sum(
                            len(bundle.workspace_context.short_term) + len(bundle.workspace_context.long_term)
                            for bundle in bundles.values()
                        ),
                        selected_action_count=len(result.plan.selected_actions),
                        conflict_count=len(result.conflicts),
                        success=result.execution.success,
                    )
                )

        return MemoryBenchmarkReport(
            records=records,
            summaries=self._summaries(records),
        )

    def _summaries(self, records: list[MemoryBenchmarkRecord]) -> list[MemoryBenchmarkSummary]:
        outputs: list[MemoryBenchmarkSummary] = []
        for backend in self.central_nodes:
            backend_records = [record for record in records if record.backend == backend]
            if not backend_records:
                continue
            outputs.append(
                MemoryBenchmarkSummary(
                    backend=backend,
                    task_count=len(backend_records),
                    avg_retrieval_latency_ms=mean(record.retrieval_latency_ms for record in backend_records),
                    avg_prompt_char_count=mean(record.prompt_char_count for record in backend_records),
                    avg_graph_fact_count=mean(record.graph_fact_count for record in backend_records),
                    avg_workspace_snippet_count=mean(record.workspace_snippet_count for record in backend_records),
                    avg_selected_action_count=mean(record.selected_action_count for record in backend_records),
                    avg_conflict_count=mean(record.conflict_count for record in backend_records),
                    success_rate=sum(1 for record in backend_records if record.success) / len(backend_records),
                )
            )
        return outputs
