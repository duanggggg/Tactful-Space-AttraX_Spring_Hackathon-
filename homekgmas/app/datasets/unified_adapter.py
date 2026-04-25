"""Canonical dataset adapters that preserve one unchanged orchestration flow."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.api.schemas import TaskRequest
from app.datahub.schemas import build_action_t, build_sample_t, build_state_t, build_task_t
from app.datasets.source_registry import DatasetSourceProfile, get_dataset_source_profile


@dataclass(frozen=True)
class UnifiedDatasetBundle:
    """One canonical bundle ready for the unchanged central orchestration flow."""

    source_profile: DatasetSourceProfile
    state_t: dict[str, Any]
    task_t: dict[str, Any]
    action_t: dict[str, Any]
    sample_t: dict[str, Any]

    def to_task_request(self) -> TaskRequest:
        """Convert the canonical task into the runtime request consumed by the same pipeline."""

        task = self.task_t
        return TaskRequest(
            task_id=str(task["task_id"]),
            description=str(task.get("raw_text") or ""),
            source=str(task.get("task_source") or "user_nl"),
            constraints={"trigger": task.get("trigger") or {}},
            preferences={
                "parsed_slots": task.get("parsed_slots") or {},
                "source_dataset": self.source_profile.source_dataset,
                "source_family": self.source_profile.source_family,
                "agent_mode": self.source_profile.agent_mode,
                "target_devices_hint": task.get("target_devices_hint") or [],
            },
        )


def build_unified_dataset_bundle(
    *,
    source_dataset: str,
    home_id: str,
    timestamp: str | None,
    task_source: str,
    raw_text: str,
    actions: list[dict[str, Any]],
    sensor_events: list[dict[str, Any]] | None = None,
    device_states: dict[str, Any] | None = None,
    occupancy: Any = None,
    activity_hint: Any = None,
    environment: dict[str, Any] | None = None,
    parsed_slots: dict[str, Any] | None = None,
    trigger: dict[str, Any] | None = None,
    target_devices_hint: list[str] | None = None,
    action_reason_type: str = "label",
    candidate_devices: list[str] | None = None,
    weak_supervision: bool = False,
    recent_history: list[dict[str, Any]] | None = None,
) -> UnifiedDatasetBundle:
    """Build one canonical bundle regardless of whether the source is fusion or web."""

    source_profile = get_dataset_source_profile(source_dataset)
    state_t = build_state_t(
        home_id=home_id,
        timestamp=timestamp,
        source_dataset=source_profile.source_dataset,
        sensor_events=sensor_events,
        device_states=device_states,
        occupancy=occupancy,
        activity_hint=activity_hint,
        environment=environment,
    )
    task_t = build_task_t(
        timestamp=timestamp,
        task_source=task_source,
        raw_text=raw_text,
        source_dataset=source_profile.source_dataset,
        parsed_slots=parsed_slots,
        trigger=trigger,
        target_devices_hint=target_devices_hint,
    )
    action_t = build_action_t(
        task_id=str(task_t["task_id"]),
        timestamp=timestamp,
        actions=actions,
        source_dataset=source_profile.source_dataset,
        action_reason_type=action_reason_type,
    )
    sample_t = build_sample_t(
        state=state_t,
        task=task_t,
        target_action=action_t,
        source_dataset=source_profile.source_dataset,
        candidate_devices=candidate_devices,
        weak_supervision=weak_supervision,
        recent_history=recent_history,
    )
    return UnifiedDatasetBundle(
        source_profile=source_profile,
        state_t=state_t,
        task_t=task_t,
        action_t=action_t,
        sample_t=sample_t,
    )
