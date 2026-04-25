"""Scheduled task helpers for future phases."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ScheduledTask(BaseModel):
    """Represents a scheduler-triggered task."""

    task_id: str
    description: str
    run_at: datetime
    constraints: dict[str, str] = Field(default_factory=dict)
    status: str = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    executed_at: Optional[datetime] = None


class InMemoryScheduler:
    """A tiny scheduler placeholder kept local for the MVP."""

    def __init__(self) -> None:
        self._tasks: list[ScheduledTask] = []

    def add_task(self, task: ScheduledTask) -> None:
        self._tasks.append(task)
        self._tasks.sort(key=lambda item: item.run_at)

    def list_tasks(self, status: Optional[str] = None) -> list[ScheduledTask]:
        if status is None:
            return list(self._tasks)
        return [task for task in self._tasks if task.status == status]

    def due_tasks(self, now: Optional[datetime] = None) -> list[ScheduledTask]:
        now = now or datetime.now(timezone.utc)
        return [
            task for task in self._tasks if task.status == "pending" and task.run_at <= now
        ]

    def mark_executed(self, task_id: str, executed_at: Optional[datetime] = None) -> ScheduledTask:
        executed_at = executed_at or datetime.now(timezone.utc)
        for task in self._tasks:
            if task.task_id == task_id:
                task.status = "completed"
                task.executed_at = executed_at
                return task
        raise KeyError(f"Unknown scheduled task: {task_id}")
