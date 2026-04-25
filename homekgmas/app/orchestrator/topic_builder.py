"""Build structured topics for agent discussion."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.environment.home_state import DeviceState, OutdoorState, SensorSnapshot


class DiscussionTopic(BaseModel):
    """Structured topic given to agents for one round of discussion."""

    task_id: str
    description: str
    source: str
    constraints: dict[str, Any] = Field(default_factory=dict)
    preferences: dict[str, Any] = Field(default_factory=dict)
    sensor_snapshot: SensorSnapshot
    outdoor_snapshot: OutdoorState = Field(default_factory=OutdoorState)
    device_state: DeviceState
    relevant_memory: list[str] = Field(default_factory=list)


class TopicBuilder:
    """Construct discussion topics from task input and environment state."""

    def build(
        self,
        task_id: str,
        description: str,
        source: str,
        constraints: dict[str, Any],
        preferences: dict[str, Any],
        sensor_snapshot: SensorSnapshot,
        outdoor_snapshot: OutdoorState,
        device_state: DeviceState,
        relevant_memory: list[str],
    ) -> DiscussionTopic:
        return DiscussionTopic(
            task_id=task_id,
            description=description,
            source=source,
            constraints=constraints,
            preferences=preferences,
            sensor_snapshot=sensor_snapshot,
            outdoor_snapshot=outdoor_snapshot,
            device_state=device_state,
            relevant_memory=relevant_memory,
        )
