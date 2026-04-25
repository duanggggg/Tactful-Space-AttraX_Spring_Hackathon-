"""Execution-planning hook for future richer planning logic."""

from __future__ import annotations

from app.planning.plan import ExecutionPlan


class ExecutionPlanner:
    """Currently passes through the coordinated plan unchanged."""

    def finalize(self, plan: ExecutionPlan) -> ExecutionPlan:
        return plan
