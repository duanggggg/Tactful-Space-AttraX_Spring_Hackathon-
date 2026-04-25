"""Execution plan models."""

from __future__ import annotations

from typing import Any
from typing import Literal

from pydantic import BaseModel, Field

from app.planning.action import PlannedAction


ConsensusLevel = Literal["low", "medium", "high"]


class ExecutedAction(PlannedAction):
    """A selected action annotated with execution status."""

    status: str = "applied"
    applied_at: str = ""
    failure_reason: str = ""


class ExecutionPlan(BaseModel):
    """The final coordinated action plan selected by the central node."""

    task_id: str
    selected_actions: list[PlannedAction] = Field(default_factory=list)
    rejected_actions: list[PlannedAction] = Field(default_factory=list)
    rationale: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    decision_confidence: float = 0.0
    consensus_level: ConsensusLevel = "medium"
    policy_checks_passed: list[str] = Field(default_factory=list)


class ExecutionResult(BaseModel):
    """Execution outcome returned by the simulator."""

    success: bool = True
    applied_actions: list[ExecutedAction] = Field(default_factory=list)
    state_snapshot: dict[str, Any] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
