"""API request and response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class TaskRequest(BaseModel):
    """Task submitted by a user or scheduler."""

    task_id: str = Field(default_factory=lambda: f"task-{uuid4().hex[:8]}")
    description: str
    source: str = "user"
    constraints: dict[str, Any] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)


class ScheduledTaskRequest(TaskRequest):
    """Request model used to register a scheduled task."""

    run_at: datetime


class ScheduledTaskResponse(BaseModel):
    """Response payload for scheduled tasks."""

    task_id: str
    description: str
    source: str
    run_at: datetime
    constraints: dict[str, Any] = Field(default_factory=dict)
    status: str = "pending"
    executed_at: Optional[datetime] = None


class RunDueTasksResponse(BaseModel):
    """Response returned when due scheduled tasks are executed."""

    triggered_at: datetime
    executed_count: int
    executed_task_ids: List[str] = Field(default_factory=list)
    skipped_task_ids: List[str] = Field(default_factory=list)
    results: List[Dict[str, Any]] = Field(default_factory=list)
