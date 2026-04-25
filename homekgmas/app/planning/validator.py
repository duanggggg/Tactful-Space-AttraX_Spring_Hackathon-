"""Minimal plan validation hooks."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.planning.plan import ExecutionPlan


class PlanValidationResult(BaseModel):
    """Validation result for a generated execution plan."""

    valid: bool
    reasons: list[str] = Field(default_factory=list)


class PlanValidator:
    """Validate simple invariants for the MVP execution plan."""

    def validate(self, plan: ExecutionPlan) -> PlanValidationResult:
        seen: set[tuple[str, str]] = set()
        action_ids: set[str] = set()
        reasons: list[str] = []

        for action in plan.selected_actions:
            key = (action.device_id, action.attribute)
            if key in seen:
                reasons.append(f"Duplicate selected action for {action.device_id}.{action.attribute}")
            seen.add(key)
            if action.action_id in action_ids:
                reasons.append(f"Duplicate action_id detected for {action.action_id}")
            action_ids.add(action.action_id)

        if not plan.rationale:
            reasons.append("Plan rationale must not be empty")

        return PlanValidationResult(valid=not reasons, reasons=reasons)
