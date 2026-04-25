"""In-memory async event bus for streaming task events to SSE subscribers."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List


class EventBus:
    def __init__(self, queue_size: int = 128) -> None:
        self._subscribers: List[asyncio.Queue[str]] = []
        self._lock = asyncio.Lock()
        self._queue_size = queue_size

    async def subscribe(self) -> asyncio.Queue[str]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=self._queue_size)
        async with self._lock:
            self._subscribers.append(queue)
        return queue

    async def unsubscribe(self, queue: asyncio.Queue[str]) -> None:
        async with self._lock:
            if queue in self._subscribers:
                self._subscribers.remove(queue)

    async def publish(self, event: str, data: Dict[str, Any]) -> None:
        payload = json.dumps(data, ensure_ascii=False, default=str)
        message = f"event: {event}\ndata: {payload}\n\n"
        async with self._lock:
            subscribers = list(self._subscribers)
        for queue in subscribers:
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                # Slow consumer: drop the oldest message and retry once
                try:
                    queue.get_nowait()
                    queue.put_nowait(message)
                except (asyncio.QueueEmpty, asyncio.QueueFull):
                    pass


_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
