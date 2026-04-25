"""Action primitives for coordinated execution."""

from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field


Priority = Literal["low", "medium", "high"]


class PlannedAction(BaseModel):
    """A single device-level action proposed by an agent."""

    action_id: str = Field(default_factory=lambda: f"action-{uuid4().hex[:8]}")
    device_id: str
    attribute: str
    value: Any
    reason: str
    requested_by: str
    priority: Priority = "medium"
    decision_reason: str = ""
