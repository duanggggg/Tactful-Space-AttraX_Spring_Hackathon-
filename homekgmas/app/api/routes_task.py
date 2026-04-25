"""Task submission routes."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.api.event_bus import get_event_bus
from app.api.schemas import (
    RunDueTasksResponse,
    ScheduledTaskRequest,
    ScheduledTaskResponse,
    TaskRequest,
)
from app.environment.home_state import HomeState
from app.orchestrator.central_node import CentralNode, OrchestrationResult
from app.planning.scheduler import InMemoryScheduler, ScheduledTask


def _to_scheduled_response(task: ScheduledTask) -> ScheduledTaskResponse:
    return ScheduledTaskResponse(
        task_id=task.task_id,
        description=task.description,
        source="scheduled",
        run_at=task.run_at,
        constraints=task.constraints,
        status=task.status,
        executed_at=task.executed_at,
    )


def build_task_router(central_node: CentralNode, scheduler: InMemoryScheduler) -> APIRouter:
    """Create the task router bound to a central node instance."""

    router = APIRouter(prefix="/tasks", tags=["tasks"])

    @router.get("/demo")
    def demo_task_usage() -> dict:
        return {
            "message": "This endpoint runs a demo orchestration task.",
            "method": "POST",
            "path": "/api/v1/tasks/demo",
            "content_type": "application/json",
            "example_body": {
                "description": "Create a cool calm evening with soft light and music"
            },
            "try_it_here": "/docs",
        }

    @router.get("/context/current", response_model=HomeState)
    def get_current_context() -> HomeState:
        return central_node.simulator.get_home_state()

    @router.post("/demo", response_model=OrchestrationResult)
    def run_demo_task(task: TaskRequest) -> OrchestrationResult:
        return central_node.handle_task(task)

    @router.post("/external", response_model=OrchestrationResult)
    async def run_external_task(task: TaskRequest) -> OrchestrationResult:
        result = await asyncio.to_thread(central_node.handle_task, task)
        await get_event_bus().publish(
            "task_result",
            {
                "task_id": task.task_id,
                "description": task.description,
                "source": task.source or "external",
                "result": result.model_dump(mode="json"),
            },
        )
        return result

    @router.get("/stream")
    async def stream_tasks(request: Request) -> StreamingResponse:
        bus = get_event_bus()
        queue = await bus.subscribe()

        async def event_gen():
            try:
                yield 'event: hello\ndata: {"ok": true}\n\n'
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        msg = await asyncio.wait_for(queue.get(), timeout=15.0)
                        yield msg
                    except asyncio.TimeoutError:
                        yield ": keepalive\n\n"
            finally:
                await bus.unsubscribe(queue)

        return StreamingResponse(
            event_gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @router.post("/scheduled", response_model=ScheduledTaskResponse)
    def create_scheduled_task(task: ScheduledTaskRequest) -> ScheduledTaskResponse:
        scheduled = ScheduledTask(
            task_id=task.task_id,
            description=task.description,
            run_at=task.run_at,
            constraints={key: str(value) for key, value in task.constraints.items()},
        )
        scheduler.add_task(scheduled)
        return _to_scheduled_response(scheduled)

    @router.get("/scheduled", response_model=List[ScheduledTaskResponse])
    def list_scheduled_tasks(status: Optional[str] = None) -> List[ScheduledTaskResponse]:
        return [_to_scheduled_response(task) for task in scheduler.list_tasks(status=status)]

    @router.post("/scheduled/run-due", response_model=RunDueTasksResponse)
    def run_due_scheduled_tasks(triggered_at: Optional[datetime] = None) -> RunDueTasksResponse:
        current_time = triggered_at or datetime.now(timezone.utc)
        due_tasks = scheduler.due_tasks(now=current_time)
        results = []
        executed_ids = []

        for scheduled_task in due_tasks:
            request = TaskRequest(
                task_id=scheduled_task.task_id,
                description=scheduled_task.description,
                source="scheduled",
                constraints=scheduled_task.constraints,
            )
            result = central_node.handle_task(request)
            scheduler.mark_executed(scheduled_task.task_id, executed_at=current_time)
            results.append(result.model_dump(mode="json"))
            executed_ids.append(scheduled_task.task_id)

        pending_ids = [task.task_id for task in scheduler.list_tasks(status="pending")]
        return RunDueTasksResponse(
            triggered_at=current_time,
            executed_count=len(executed_ids),
            executed_task_ids=executed_ids,
            skipped_task_ids=pending_ids,
            results=results,
        )

    return router
