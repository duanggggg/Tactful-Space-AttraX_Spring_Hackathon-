"""Shared unified schema constructors."""

from __future__ import annotations

from typing import Any

from app.datahub.normalize import infer_time_context, safe_json, split_for_id, stable_id


def build_state_t(
    *,
    home_id: str,
    timestamp: str | None,
    source_dataset: str,
    sensor_events: list[dict[str, Any]] | None = None,
    device_states: dict[str, Any] | None = None,
    occupancy: Any = None,
    activity_hint: Any = None,
    environment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Construct a normalized state_t object."""

    environment = safe_json(environment or {})
    inferred = infer_time_context(timestamp)
    merged_environment = {
        "time_of_day": environment.get("time_of_day") or inferred.get("time_of_day"),
        "day_of_week": environment.get("day_of_week") or inferred.get("day_of_week"),
        "weather": environment.get("weather"),
        "temperature": environment.get("temperature"),
        **environment,
    }
    return {
        "home_id": home_id,
        "timestamp": timestamp,
        "sensor_events": safe_json(sensor_events or []),
        "device_states": safe_json(device_states or {}),
        "occupancy": safe_json(occupancy),
        "activity_hint": safe_json(activity_hint),
        "environment": merged_environment,
        "source_dataset": source_dataset,
    }


def build_task_t(
    *,
    timestamp: str | None,
    task_source: str,
    raw_text: str,
    source_dataset: str,
    parsed_slots: dict[str, Any] | None = None,
    trigger: dict[str, Any] | None = None,
    target_devices_hint: list[str] | None = None,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Construct a normalized task_t object."""

    task_id = task_id or f"task-{stable_id(source_dataset, timestamp, raw_text)}"
    return {
        "task_id": task_id,
        "timestamp": timestamp,
        "task_source": task_source,
        "raw_text": raw_text,
        "parsed_slots": safe_json(parsed_slots or {}),
        "trigger": safe_json(trigger or {"type": "event", "detail": None}),
        "target_devices_hint": safe_json(target_devices_hint or []),
        "source_dataset": source_dataset,
    }


def build_action_t(
    *,
    task_id: str,
    timestamp: str | None,
    actions: list[dict[str, Any]],
    source_dataset: str,
    action_reason_type: str,
) -> dict[str, Any]:
    """Construct a normalized action_t object."""

    return {
        "task_id": task_id,
        "timestamp": timestamp,
        "actions": safe_json(actions),
        "action_reason_type": action_reason_type,
        "source_dataset": source_dataset,
    }


def build_sample_t(
    *,
    state: dict[str, Any],
    task: dict[str, Any],
    target_action: dict[str, Any],
    source_dataset: str,
    candidate_devices: list[str] | None = None,
    split_key: str | None = None,
    sample_id: str | None = None,
    weak_supervision: bool = False,
    recent_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Construct a normalized sample_t object."""

    split_key = split_key or state.get("home_id") or task.get("task_id") or source_dataset
    sample_id = sample_id or f"sample-{stable_id(source_dataset, task.get('task_id'), state.get('timestamp'))}"
    return {
        "sample_id": sample_id,
        "state": safe_json(state),
        "task": safe_json(task),
        "target_action": safe_json(target_action),
        "candidate_devices": safe_json(candidate_devices or []),
        "split": split_for_id(split_key),
        "source_dataset": source_dataset,
        "weak_supervision": weak_supervision,
        "recent_history": safe_json(recent_history or []),
    }

