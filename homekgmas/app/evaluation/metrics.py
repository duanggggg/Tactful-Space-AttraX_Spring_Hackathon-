"""Basic evaluation metrics for the local MVP."""

from __future__ import annotations

from pydantic import BaseModel

from app.orchestrator.central_node import OrchestrationResult


class RunMetrics(BaseModel):
    """Compact metrics for one orchestration run."""

    task_id: str
    success: bool
    selected_agent_count: int
    selected_action_count: int
    conflict_count: int
    rounds_completed: int


def build_run_metrics(result: OrchestrationResult, rounds_completed: int) -> RunMetrics:
    """Convert an orchestration result into compact metrics."""

    return RunMetrics(
        task_id=result.task_id,
        success=result.execution.success,
        selected_agent_count=len(result.selected_agents),
        selected_action_count=len(result.plan.selected_actions),
        conflict_count=len(result.conflicts),
        rounds_completed=rounds_completed,
    )
