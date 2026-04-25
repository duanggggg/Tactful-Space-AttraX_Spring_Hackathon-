"""Offline dataset evaluation against episode-level warehouse samples."""

from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path
import time
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field

try:
    from tqdm.auto import tqdm
except Exception:  # pragma: no cover - fallback when tqdm is unavailable
    tqdm = None

from app.agents.agent_registry import AgentRegistry
from app.api.schemas import TaskRequest
from app.core.config import build_settings
from app.core.constants import AGENT_NAMES
from app.discussion.protocol import AgentDialogueEntry
from app.environment.home_state import DeviceState, HomeState, OutdoorState, SensorSnapshot
from app.environment.simulator import HomeSimulator, SimulatorBackend
from app.memory.coordinator import MemoryCoordinator
from app.memory.graph_retriever import GraphRetriever
from app.memory.triple_store import TripleStore
from app.memory.workspace_store import WorkspaceMemoryStore
from app.orchestrator.central_node import CentralNode, OrchestrationResult
from app.planning.action import PlannedAction
from app.datasets.source_registry import get_dataset_source_profile


DOMAIN_TO_AGENT = {
    "climate": "cooling_agent",
    "light": "lighting_agent",
    "media_player": "music_agent",
    "fan": "fan_agent",
    "cover": "cover_agent",
    "lock": "lock_agent",
    "switch": "switch_agent",
    "appliance": "appliance_agent",
    "vacuum": "appliance_agent",
}

ACTIONABLE_DOMAINS = set(DOMAIN_TO_AGENT)

WEB_PARAMETER_NAMES = {"temperature", "humidity", "air", "brightness", "noise", "energy"}
WEB_ROOM_KEYS = ("living_room", "bedroom")
WEB_DATASET_FAMILY = "web"
WEB_ROOM_WEIGHTS_DEFAULT = {"living_room": 0.5, "bedroom": 0.5}
WEB_ROOM_PARAMETER_WEIGHTS = {
    "living_room": {
        "air": 0.22,
        "temperature": 0.20,
        "brightness": 0.18,
        "noise": 0.16,
        "humidity": 0.14,
        "energy": 0.10,
    },
    "bedroom": {
        "noise": 0.25,
        "temperature": 0.22,
        "air": 0.18,
        "humidity": 0.16,
        "brightness": 0.12,
        "energy": 0.07,
    },
}


class WebEvalMetrics(BaseModel):
    """Additional web-only metrics appended after the base evaluation flow."""

    evaluated: bool = False
    has_explicit_demand: bool = False
    comfort_score: float | None = None
    comfort_improvement: float | None = None
    demand_satisfaction: float | None = None
    energy_cost: float | None = None
    energy_efficiency: float | None = None
    hard_conflict_count: int = 0
    soft_conflict_cost: float = 0.0
    synergy_bonus: float = 0.0
    coordination_score: float | None = None
    action_utility: float | None = None
    action_clarity: float | None = None
    room_scores_json: dict[str, float] = Field(default_factory=dict)
    parameter_scores_json: dict[str, dict[str, float]] = Field(default_factory=dict)
    demand_breakdown_json: dict[str, float] = Field(default_factory=dict)


class WebEvalSummary(BaseModel):
    """Aggregated summary for web-only evaluation metrics."""

    sample_count: int
    evaluated_sample_count: int
    avg_comfort_score: float | None = None
    avg_comfort_improvement: float | None = None
    avg_demand_satisfaction: float | None = None
    avg_energy_cost: float | None = None
    avg_energy_efficiency: float | None = None
    avg_hard_conflict_count: float | None = None
    avg_soft_conflict_cost: float | None = None
    avg_synergy_bonus: float | None = None
    avg_coordination_score: float | None = None
    avg_action_utility: float | None = None
    avg_action_clarity: float | None = None


class DatasetEvalRecord(BaseModel):
    """One evaluated episode with scalar metrics."""

    sample_id: str
    source_dataset: str
    task_source: str
    label_quality: str
    gold_action_count: int
    predicted_action_count: int
    proposal_action_count: int
    selected_agent_count: int
    discussion_turn_count: int
    conflict_count: int
    execution_success: bool
    latency_ms: float
    wakeup_agent_precision: float
    wakeup_agent_recall: float
    wakeup_agent_f1: float
    wakeup_agent_exact_match: bool
    proposal_domain_precision: float
    proposal_domain_recall: float
    proposal_domain_f1: float
    proposal_action_precision: float
    proposal_action_recall: float
    proposal_action_f1: float
    final_domain_precision: float
    final_domain_recall: float
    final_domain_f1: float
    final_service_precision: float
    final_service_recall: float
    final_service_f1: float
    final_action_precision: float
    final_action_recall: float
    final_action_f1: float
    final_domain_exact_match: bool
    final_action_exact_match: bool
    action_count_abs_error: int
    selected_agents_json: list[str] = Field(default_factory=list)
    gold_agents_json: list[str] = Field(default_factory=list)
    predicted_domains_json: list[str] = Field(default_factory=list)
    gold_domains_json: list[str] = Field(default_factory=list)
    web_metrics: WebEvalMetrics | None = None


class DatasetEvalSummary(BaseModel):
    """Aggregated metrics for one evaluation run."""

    sample_count: int
    execution_success_rate: float
    avg_latency_ms: float
    avg_conflict_count: float
    avg_selected_agent_count: float
    avg_predicted_action_count: float
    avg_gold_action_count: float
    avg_action_count_abs_error: float
    wakeup_agent_f1: float
    proposal_domain_f1: float
    proposal_action_f1: float
    final_domain_f1: float
    final_service_f1: float
    final_action_f1: float
    wakeup_agent_exact_match_rate: float
    final_domain_exact_match_rate: float
    final_action_exact_match_rate: float


class DatasetEvalReport(BaseModel):
    """Top-level dataset evaluation payload."""

    generated_at: str
    config: dict[str, Any]
    summary: DatasetEvalSummary
    web_summary: WebEvalSummary | None = None
    by_source_dataset: dict[str, DatasetEvalSummary] = Field(default_factory=dict)
    by_task_source: dict[str, DatasetEvalSummary] = Field(default_factory=dict)
    by_label_quality: dict[str, DatasetEvalSummary] = Field(default_factory=dict)
    web_by_source_dataset: dict[str, WebEvalSummary] = Field(default_factory=dict)
    records: list[DatasetEvalRecord] = Field(default_factory=list)


def _parse_json_like(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, float) and pd.isna(value):
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        return json.loads(stripped)
    return value


def _time_of_day_from_ts(timestamp: str | None) -> str:
    if not timestamp:
        return "evening"
    try:
        dt = datetime.fromisoformat(str(timestamp))
    except ValueError:
        return "evening"
    hour = dt.hour
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"


def _quiet_hours_from_ts(timestamp: str | None) -> bool:
    if not timestamp:
        return False
    try:
        hour = datetime.fromisoformat(str(timestamp)).hour
    except ValueError:
        return False
    return hour >= 22 or hour < 7


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_room_name(text: str) -> str:
    lowered = str(text).lower()
    if "bed" in lowered:
        return "bedroom"
    if "living" in lowered or "kitchen" in lowered:
        return "living_room"
    return "living_room"


def build_home_state_from_snapshot(state_row: dict[str, Any]) -> HomeState:
    """Convert one canonical warehouse state row into the local simulator state."""

    sensors = SensorSnapshot()
    devices = DeviceState()
    outdoor = OutdoorState()

    snapshot_ts = state_row.get("snapshot_ts")
    sensors.current_time = str(snapshot_ts or sensors.current_time)
    sensors.time_of_day = _time_of_day_from_ts(snapshot_ts)
    sensors.quiet_hours = _quiet_hours_from_ts(snapshot_ts)

    environment = _parse_json_like(state_row.get("environment_json")) or {}
    sensor_summary = _parse_json_like(state_row.get("sensor_summary_json")) or {}
    device_state = _parse_json_like(state_row.get("device_state_json")) or {}

    if isinstance(environment, dict):
        sensors.time_of_day = str(environment.get("time_of_day") or sensors.time_of_day)
        sensors.room_temperature_c = _safe_float(environment.get("temperature"), sensors.room_temperature_c)
        outdoor.weather = str(environment.get("weather") or outdoor.weather)
        outdoor.outdoor_temperature_c = _safe_float(
            environment.get("temperature") or environment.get("outdoor_temperature_c"),
            outdoor.outdoor_temperature_c,
        )

    occupancy_status = state_row.get("occupancy_status")
    if isinstance(occupancy_status, bool):
        sensors.occupancy["living_room"] = occupancy_status
    elif isinstance(occupancy_status, str):
        lowered = occupancy_status.lower()
        if lowered in {"occupied", "home", "present", "true"}:
            sensors.occupancy["living_room"] = True
        elif lowered in {"vacant", "away", "false"}:
            sensors.occupancy["living_room"] = False

    if isinstance(sensor_summary, dict):
        active_rooms = sensor_summary.get("distinct_active_rooms") or []
        if isinstance(active_rooms, list):
            sensors.occupancy["living_room"] = any("living" in str(room).lower() for room in active_rooms) or sensors.occupancy["living_room"]
            sensors.occupancy["bedroom"] = any("bed" in str(room).lower() for room in active_rooms) or sensors.occupancy["bedroom"]
        if sensor_summary.get("door_open_counts"):
            sensors.occupancy["living_room"] = True

    if isinstance(device_state, dict):
        for entity_id, payload in device_state.items():
            entity = str(entity_id).lower()
            state_value = None
            attributes: dict[str, Any] = {}
            if isinstance(payload, dict):
                state_value = payload.get("state")
                raw_attrs = payload.get("attributes")
                if isinstance(raw_attrs, dict):
                    attributes = raw_attrs
            if entity.startswith("light."):
                target = devices.bedroom_lamp if "bed" in entity else devices.lights["living_room_main"]
                target.power = str(state_value).lower() == "on"
                target.brightness = _safe_int(attributes.get("brightness"), target.brightness)
            elif entity.startswith("climate.") or entity.startswith("air_conditioner."):
                target = devices.air_conditioners["bedroom_ac_1"] if "bed" in entity else devices.air_conditioners["living_room_ac_1"]
                target.power = str(state_value).lower() == "on"
                target.target_temperature = _safe_int(
                    attributes.get("temperature") or attributes.get("target_temperature"),
                    target.target_temperature,
                )
            elif entity.startswith("media_player.") or entity.startswith("speaker."):
                devices.music_player.power = str(state_value).lower() == "on"
                devices.music_player.volume = _safe_int(attributes.get("volume_level"), devices.music_player.volume)
            elif entity.startswith("cover."):
                target = devices.covers["bedroom_blinds"] if "bed" in entity else devices.covers["living_room_curtain"]
                raw_position = str(state_value or attributes.get("position") or target.position).lower()
                target.position = "closed" if raw_position in {"closed", "close"} else "open" if raw_position in {"open", "opened"} else "half"
            elif entity.startswith("lock."):
                devices.locks["front_door_lock"].locked = str(state_value).lower() not in {"unlocked", "unlock", "off"}
            elif entity.startswith("fan."):
                target = devices.fans["bedroom_fan_1"] if "bed" in entity else devices.fans["living_room_fan_1"]
                target.power = str(state_value).lower() == "on"
                target.speed = str(attributes.get("percentage") or target.speed).lower()
            elif entity.startswith("switch."):
                target = devices.switches["bedroom_humidifier"] if "humid" in entity or "bed" in entity else devices.switches["air_purifier"]
                target.power = str(state_value).lower() == "on"
            elif entity.startswith("vacuum."):
                devices.appliances["robot_vacuum_1"].power = str(state_value).lower() == "on"
                devices.appliances["robot_vacuum_1"].status = str(state_value or devices.appliances["robot_vacuum_1"].status).lower()

    return HomeState(sensors=sensors, devices=devices, outdoor=outdoor)


def build_task_request_from_rows(task_row: dict[str, Any], state_row: dict[str, Any]) -> TaskRequest:
    """Build a task request suitable for the current orchestration pipeline."""

    raw_text = task_row.get("raw_text")
    parsed = _parse_json_like(task_row.get("parsed_slots_json")) or {}
    trigger = _parse_json_like(task_row.get("trigger_json")) or {}
    state_history = _parse_json_like(state_row.get("history_action_summary_json")) or []
    description = str(raw_text).strip() if isinstance(raw_text, str) and raw_text.strip() else ""

    if not description:
        task_source = str(task_row.get("task_source") or "inferred")
        if task_source == "inferred":
            history_hint = ""
            if isinstance(state_history, list) and state_history:
                top_items = []
                for item in state_history[:3]:
                    if not isinstance(item, dict):
                        continue
                    device_name = str(item.get("device_name") or item.get("domain") or "device")
                    top_items.append(device_name)
                if top_items:
                    history_hint = " Recent activity involved " + ", ".join(top_items) + "."
            description = "Decide the next smart-home action based on recent home activity." + history_hint
        elif task_source == "routine":
            description = "Apply the user's routine in the current home context."
        elif task_source == "automation":
            description = "Execute the automation that matches the current trigger and state."
        else:
            device = parsed.get("device") or parsed.get("entity") or parsed.get("target_device")
            room = parsed.get("room") or parsed.get("area")
            action = parsed.get("action") or parsed.get("intent") or trigger.get("type")
            fragments = [
                "Handle the smart-home request",
                f"for {device}" if device else "",
                f"in the {room}" if room else "",
                f"with action {action}" if action else "",
            ]
            description = " ".join(fragment for fragment in fragments if fragment).strip() + "."

    return TaskRequest(
        task_id=str(task_row["task_id"]),
        description=description,
        source=str(task_row.get("task_source") or "dataset"),
        constraints={"trigger": trigger},
        preferences={"parsed_slots": parsed, "source_dataset": task_row.get("source_dataset")},
    )


def infer_domain_from_device_id(device_id: str) -> str:
    """Infer one canonical device domain from the local simulator device id."""

    lowered = str(device_id).lower()
    if lowered in {"living_room_main", "bedroom_lamp"}:
        return "light"
    if lowered == "music_player":
        return "media_player"
    if lowered in {"air_purifier", "bedroom_humidifier"}:
        return "switch"
    if lowered == "front_door_lock":
        return "lock"
    if lowered == "robot_vacuum_1":
        return "appliance"
    if "ac" in lowered or "climate" in lowered:
        return "climate"
    if "light" in lowered or "lamp" in lowered:
        return "light"
    if "music" in lowered or "speaker" in lowered or "television" in lowered or "tv" in lowered:
        return "media_player"
    if "fan" in lowered:
        return "fan"
    if "curtain" in lowered or "blind" in lowered:
        return "cover"
    if "lock" in lowered:
        return "lock"
    if "purifier" in lowered or "humidifier" in lowered or "switch" in lowered:
        return "switch"
    if "vacuum" in lowered or "robot" in lowered or "appliance" in lowered:
        return "appliance"
    return "other"


def infer_service_from_predicted_action(action: PlannedAction) -> str:
    """Map one predicted action into the warehouse service enum."""

    attribute = str(action.attribute).lower()
    value = action.value
    if attribute == "power":
        return "turn_on" if bool(value) else "turn_off"
    if attribute == "locked":
        return "lock" if bool(value) else "unlock"
    if attribute == "target_temperature":
        return "set_temperature"
    if attribute == "brightness":
        return "set_brightness"
    if attribute == "position":
        lowered = str(value).lower()
        if lowered == "open":
            return "open"
        if lowered == "closed":
            return "close"
    return "custom"


def infer_service_from_target_action(action: dict[str, Any]) -> str:
    """Map one target action row into a comparable service enum."""

    service = str(action.get("service_name_norm") or "custom").lower()
    if service != "custom":
        return service
    arguments = action.get("arguments_json") or {}
    if isinstance(arguments, str):
        arguments = _parse_json_like(arguments) or {}
    if not isinstance(arguments, dict):
        arguments = {}
    state_value = arguments.get("state")
    if str(state_value).lower() in {"on", "true", "1"}:
        return "turn_on"
    if str(state_value).lower() in {"off", "false", "0"}:
        return "turn_off"
    attr = str(arguments.get("attribute") or arguments.get("attr") or "").lower()
    if "temperature" in attr:
        return "set_temperature"
    if "humidity" in attr:
        return "set_humidity"
    if "brightness" in attr:
        return "set_brightness"
    position = str(arguments.get("position") or "").lower()
    if position == "open":
        return "open"
    if position in {"close", "closed"}:
        return "close"
    if any(key in arguments for key in ("temperature", "fan_speed", "mode", "volume", "playlist", "input_source", "equalizer", "media_track", "color", "armed", "alarm_volume", "humidity")):
        return "custom"
    return "custom"


def infer_gold_agents(target_actions: list[dict[str, Any]], task_text: str | None = None) -> set[str]:
    """Infer the gold agent set from target action domains and task text."""

    agents = {
        DOMAIN_TO_AGENT[action.get("device_domain") or action.get("domain")]
        for action in target_actions
        if (action.get("device_domain") or action.get("domain")) in DOMAIN_TO_AGENT
    }
    text = (task_text or "").lower()
    if not agents:
        if any(keyword in text for keyword in ("purifier", "humidifier", "air cleaner", "fresh", "air")):
            agents.add("switch_agent")
        if any(keyword in text for keyword in ("music", "speaker", "playlist", "tv", "television")):
            agents.add("music_agent")
    return agents


def normalize_target_actions(target_actions: list[dict[str, Any]]) -> dict[str, set[str]]:
    """Convert target actions to comparable token sets."""

    domains: set[str] = set()
    services: set[str] = set()
    action_tokens: set[str] = set()
    for action in target_actions:
        domain = str(action.get("device_domain") or action.get("domain") or "other")
        service = infer_service_from_target_action(action)
        domains.add(domain)
        services.add(service)
        action_tokens.add(f"{domain}:{service}")
    return {
        "domains": domains,
        "services": services,
        "actions": action_tokens,
    }


def normalize_predicted_actions(actions: list[PlannedAction]) -> dict[str, set[str]]:
    """Convert predicted planned actions to comparable token sets."""

    domains: set[str] = set()
    services: set[str] = set()
    action_tokens: set[str] = set()
    for action in actions:
        domain = infer_domain_from_device_id(action.device_id)
        service = infer_service_from_predicted_action(action)
        domains.add(domain)
        services.add(service)
        action_tokens.add(f"{domain}:{service}")
    return {
        "domains": domains,
        "services": services,
        "actions": action_tokens,
    }


def _precision_recall_f1(predicted: set[str], gold: set[str]) -> tuple[float, float, float]:
    if not predicted and not gold:
        return 1.0, 1.0, 1.0
    if not predicted or not gold:
        return 0.0, 0.0, 0.0
    true_positive = len(predicted & gold)
    precision = true_positive / len(predicted) if predicted else 0.0
    recall = true_positive / len(gold) if gold else 0.0
    f1 = 0.0 if precision + recall == 0 else (2 * precision * recall) / (precision + recall)
    return precision, recall, f1


def _clamp_score(value: float, *, lower: float = 0.0, upper: float = 1.0) -> float:
    return max(lower, min(upper, float(value)))


def _score_temperature(value: float, *, room: str, task_text: str) -> float:
    task_lower = task_text.lower()
    if any(keyword in task_lower for keyword in ("sleep", "rest", "bedtime")) and room == "bedroom":
        target = 23.0
    elif any(keyword in task_lower for keyword in ("warm", "heating", "heat")):
        target = 22.0
    elif any(keyword in task_lower for keyword in ("cool", "cooling", "hot", "stuffy", "movie", "video")):
        target = 24.0 if room == "living_room" else 23.5
    else:
        target = 24.5 if room == "living_room" else 23.8
    return _clamp_score(1.0 - (abs(float(value) - target) / 8.0))


def _score_humidity(value: float) -> float:
    humidity = float(value)
    if 40.0 <= humidity <= 60.0:
        return 1.0
    tolerance = 30.0
    if humidity > 60.0:
        return _clamp_score(1.0 - ((humidity - 60.0) / tolerance))
    return _clamp_score(1.0 - ((40.0 - humidity) / tolerance))


def _score_air(value: float) -> float:
    return _clamp_score((float(value) - 30.0) / 50.0)


def _score_brightness(value: float, *, room: str, task_text: str) -> float:
    task_lower = task_text.lower()
    if any(keyword in task_lower for keyword in ("movie", "video", "watch")):
        target = 16.0 if room == "living_room" else 12.0
    elif any(keyword in task_lower for keyword in ("sleep", "rest", "bedtime")):
        target = 10.0 if room == "living_room" else 6.0
    elif any(keyword in task_lower for keyword in ("work", "study", "focus", "read", "reading")):
        target = 72.0 if room == "living_room" else 60.0
    elif any(keyword in task_lower for keyword in ("dim", "cozy", "soft", "relax")):
        target = 24.0 if room == "living_room" else 18.0
    else:
        target = 42.0 if room == "living_room" else 30.0
    return _clamp_score(1.0 - (abs(float(value) - target) / 80.0))


def _score_noise(value: float, *, room: str, task_text: str) -> float:
    task_lower = task_text.lower()
    if any(keyword in task_lower for keyword in ("sleep", "rest", "bedtime")):
        target = 18.0 if room == "bedroom" else 24.0
    elif any(keyword in task_lower for keyword in ("movie", "video", "music")):
        target = 45.0
    else:
        target = 35.0
    noise = float(value)
    if noise <= target:
        return 1.0
    return _clamp_score(1.0 - ((noise - target) / 45.0))


def _score_energy(value: float) -> float:
    return _clamp_score(1.0 - (float(value) / 100.0))


def _normalize_web_room_key(key: str) -> str | None:
    lowered = str(key).strip().lower()
    if lowered in {"living", "living_room", "living-room"}:
        return "living_room"
    if lowered in {"bedroom", "bed_room"}:
        return "bedroom"
    return None


def _normalize_web_parameter_key(key: str) -> str | None:
    lowered = str(key).strip().lower()
    aliases = {
        "temp": "temperature",
        "temperature": "temperature",
        "humidity": "humidity",
        "air": "air",
        "air_quality": "air",
        "brightness": "brightness",
        "light": "brightness",
        "noise": "noise",
        "energy": "energy",
    }
    return aliases.get(lowered)


def _extract_web_state(raw: Any) -> dict[str, dict[str, float]] | None:
    """Extract a web-style room/outdoor state from a loosely structured payload."""

    payload = _parse_json_like(raw) if not isinstance(raw, dict) else raw
    if not isinstance(payload, dict):
        return None

    output: dict[str, dict[str, float]] = {room: {} for room in WEB_ROOM_KEYS}
    output["outdoor"] = {}

    def assign(room_key: str, parameter_key: str, value: Any) -> None:
        normalized_parameter = _normalize_web_parameter_key(parameter_key)
        if normalized_parameter is None:
            return
        try:
            output[room_key][normalized_parameter] = float(value)
        except (TypeError, ValueError):
            return

    for key, value in payload.items():
        normalized_room = _normalize_web_room_key(key)
        if normalized_room and isinstance(value, dict):
            for nested_key, nested_value in value.items():
                assign(normalized_room, nested_key, nested_value)
            continue
        if str(key).strip().lower() == "indoor" and isinstance(value, dict):
            for room_key, room_payload in value.items():
                normalized_room = _normalize_web_room_key(room_key)
                if normalized_room and isinstance(room_payload, dict):
                    for nested_key, nested_value in room_payload.items():
                        assign(normalized_room, nested_key, nested_value)
            continue
        if str(key).strip().lower() == "outdoor" and isinstance(value, dict):
            for nested_key, nested_value in value.items():
                normalized_parameter = _normalize_web_parameter_key(nested_key)
                if normalized_parameter is not None:
                    try:
                        output["outdoor"][normalized_parameter] = float(nested_value)
                    except (TypeError, ValueError):
                        pass
            continue
        lowered = str(key).strip().lower()
        if lowered.startswith("outdoor_"):
            assign("outdoor", lowered.removeprefix("outdoor_"), value)
            continue
        for room_prefix in ("living_", "bedroom_"):
            if lowered.startswith(room_prefix):
                room_key = "living_room" if room_prefix == "living_" else "bedroom"
                assign(room_key, lowered.removeprefix(room_prefix), value)
                break

    has_room_content = any(output[room] for room in WEB_ROOM_KEYS)
    if not has_room_content:
        return None
    return output


def _infer_web_action_family(action: PlannedAction) -> tuple[str, str]:
    device_id = str(action.device_id).lower()
    room = "bedroom" if "bed" in device_id else "living_room"
    if "window" in device_id:
        return "window", room
    if "curtain" in device_id or "blind" in device_id or "cover" in device_id:
        return "curtain", room
    if "fresh" in device_id or "vent" in device_id or "hrv" in device_id or "erv" in device_id:
        return "fresh_air", room
    if "dehumid" in device_id:
        return "dehumidifier", room
    if "computer" in device_id or "screen" in device_id or "monitor" in device_id:
        return "computer", room
    if device_id in {"music_player", "television", "tv"}:
        return "computer", room
    if "fan" in device_id:
        return "fan", room
    if "light" in device_id or "lamp" in device_id or device_id in {"living_room_main", "bedroom_lamp"}:
        return "light", room
    if "ac" in device_id or "climate" in device_id:
        return "air_conditioner", room
    return "other", room


def _project_web_state_after(
    before_state: dict[str, dict[str, float]],
    actions: list[PlannedAction],
) -> dict[str, dict[str, float]]:
    """Approximate a web-style post-action state when no dedicated web snapshot exists yet."""

    projected = deepcopy(before_state)
    for room in WEB_ROOM_KEYS:
        projected.setdefault(room, {})
    projected.setdefault("outdoor", {})

    def adjust(room: str, parameter: str, delta: float) -> None:
        if parameter not in projected.get(room, {}):
            return
        projected[room][parameter] = float(projected[room][parameter]) + delta

    def set_near(room: str, parameter: str, target: float, ratio: float = 0.35) -> None:
        if parameter not in projected.get(room, {}):
            return
        current = float(projected[room][parameter])
        projected[room][parameter] = current + ((target - current) * ratio)

    outdoor_humidity = float(projected.get("outdoor", {}).get("humidity", 60.0))
    outdoor_brightness = float(projected.get("outdoor", {}).get("brightness", 50.0))

    for action in actions:
        family, room = _infer_web_action_family(action)
        attr = str(action.attribute).lower()
        value = action.value

        if family == "air_conditioner":
            if attr == "target_temperature":
                try:
                    set_near(room, "temperature", float(value), ratio=0.42)
                except (TypeError, ValueError):
                    pass
                adjust(room, "energy", 14.0)
                adjust(room, "noise", 4.0)
            elif attr == "power":
                if bool(value):
                    adjust(room, "energy", 10.0)
                    adjust(room, "noise", 3.0)
                    adjust(room, "humidity", -2.0)
                else:
                    adjust(room, "energy", -6.0)
                    adjust(room, "noise", -2.0)
            elif attr == "mode" and str(value).lower() == "dry":
                adjust(room, "humidity", -6.0)
                adjust(room, "energy", 6.0)
            elif attr == "fan_speed":
                adjust(room, "noise", 1.5)
        elif family == "window":
            lowered = str(value).lower()
            if lowered == "open":
                adjust(room, "air", 10.0)
                adjust(room, "brightness", outdoor_brightness * 0.12)
                adjust(room, "noise", 6.0)
                adjust(room, "humidity", (outdoor_humidity - projected[room].get("humidity", outdoor_humidity)) * 0.18)
            elif lowered == "closed":
                adjust(room, "noise", -3.0)
                adjust(room, "brightness", -8.0)
            else:
                adjust(room, "air", 4.0)
                adjust(room, "noise", 2.5)
                adjust(room, "brightness", outdoor_brightness * 0.05)
        elif family == "curtain":
            lowered = str(value).lower()
            if lowered == "closed":
                adjust(room, "brightness", -18.0)
                adjust(room, "temperature", -0.6)
            elif lowered == "open":
                adjust(room, "brightness", 18.0)
                adjust(room, "temperature", 0.8)
            else:
                adjust(room, "brightness", 5.0)
        elif family == "fan":
            if attr == "power":
                if bool(value):
                    adjust(room, "temperature", -0.7)
                    adjust(room, "noise", 3.0)
                    adjust(room, "energy", 4.0)
                else:
                    adjust(room, "noise", -2.0)
            elif attr == "speed":
                adjust(room, "temperature", -0.5)
                adjust(room, "noise", 2.5)
                adjust(room, "energy", 2.5)
        elif family == "fresh_air":
            if attr == "power" and bool(value):
                adjust(room, "air", 8.0)
                adjust(room, "noise", 3.0)
                adjust(room, "energy", 5.0)
            elif attr in {"flow_level", "mode"}:
                adjust(room, "air", 5.0)
                adjust(room, "noise", 2.0)
                adjust(room, "energy", 3.0)
                adjust(room, "humidity", (outdoor_humidity - projected[room].get("humidity", outdoor_humidity)) * 0.10)
        elif family == "dehumidifier":
            if attr == "power" and bool(value):
                adjust(room, "humidity", -7.0)
                adjust(room, "noise", 3.0)
                adjust(room, "energy", 6.0)
            elif attr in {"humidity", "target_humidity"}:
                try:
                    set_near(room, "humidity", float(value), ratio=0.38)
                except (TypeError, ValueError):
                    pass
                adjust(room, "energy", 4.0)
        elif family == "light":
            if attr == "brightness":
                try:
                    set_near(room, "brightness", float(value), ratio=0.65)
                except (TypeError, ValueError):
                    pass
                adjust(room, "energy", max(2.0, float(value) * 0.06))
            elif attr == "power":
                if bool(value):
                    adjust(room, "brightness", 12.0)
                    adjust(room, "energy", 3.0)
                else:
                    adjust(room, "brightness", -10.0)
                    adjust(room, "energy", -2.0)
        elif family == "computer":
            if attr == "power":
                if bool(value):
                    adjust(room, "noise", 3.0)
                    adjust(room, "brightness", 4.0)
                    adjust(room, "energy", 6.0)
                    adjust(room, "temperature", 0.2)
                else:
                    adjust(room, "noise", -2.0)
                    adjust(room, "energy", -4.0)
            elif attr in {"volume", "playlist", "media_track", "input_source"}:
                adjust(room, "noise", 4.0 if attr != "volume" else max(1.0, float(value) * 0.08 if isinstance(value, (int, float)) else 3.0))
                adjust(room, "energy", 2.0)
            elif attr == "brightness":
                adjust(room, "brightness", max(2.0, float(value) * 0.04 if isinstance(value, (int, float)) else 3.0))
            elif attr == "equalizer":
                adjust(room, "noise", 1.0)

    for room in WEB_ROOM_KEYS:
        if "temperature" in projected[room]:
            projected[room]["temperature"] = round(_clamp_score(projected[room]["temperature"], lower=10.0, upper=40.0), 3)
        if "humidity" in projected[room]:
            projected[room]["humidity"] = round(_clamp_score(projected[room]["humidity"], lower=10.0, upper=100.0), 3)
        for parameter in ("air", "brightness", "noise", "energy"):
            if parameter in projected[room]:
                projected[room][parameter] = round(_clamp_score(projected[room][parameter], lower=0.0, upper=100.0), 3)
    return projected


def _score_web_state(
    state: dict[str, dict[str, float]],
    *,
    task_text: str,
) -> tuple[float, dict[str, float], dict[str, dict[str, float]]]:
    room_weights = dict(WEB_ROOM_WEIGHTS_DEFAULT)
    task_lower = task_text.lower()
    if "bedroom" in task_lower:
        room_weights = {"living_room": 0.3, "bedroom": 0.7}
    elif "living room" in task_lower or "living_room" in task_lower:
        room_weights = {"living_room": 0.7, "bedroom": 0.3}

    room_scores: dict[str, float] = {}
    parameter_scores: dict[str, dict[str, float]] = {}
    for room in WEB_ROOM_KEYS:
        room_payload = state.get(room, {})
        parameter_scores[room] = {}
        for parameter, weight in WEB_ROOM_PARAMETER_WEIGHTS[room].items():
            value = room_payload.get(parameter)
            if value is None:
                continue
            if parameter == "temperature":
                parameter_scores[room][parameter] = _score_temperature(value, room=room, task_text=task_text)
            elif parameter == "humidity":
                parameter_scores[room][parameter] = _score_humidity(value)
            elif parameter == "air":
                parameter_scores[room][parameter] = _score_air(value)
            elif parameter == "brightness":
                parameter_scores[room][parameter] = _score_brightness(value, room=room, task_text=task_text)
            elif parameter == "noise":
                parameter_scores[room][parameter] = _score_noise(value, room=room, task_text=task_text)
            elif parameter == "energy":
                parameter_scores[room][parameter] = _score_energy(value)
        room_scores[room] = round(
            sum(WEB_ROOM_PARAMETER_WEIGHTS[room][parameter] * score for parameter, score in parameter_scores[room].items()),
            4,
        )

    comfort_score = round(sum(room_weights[room] * room_scores.get(room, 0.0) for room in WEB_ROOM_KEYS), 4)
    return comfort_score, room_scores, parameter_scores


def _score_web_demand_satisfaction(
    *,
    task_text: str,
    after_parameter_scores: dict[str, dict[str, float]],
    selected_actions: list[PlannedAction],
) -> tuple[bool, float | None, dict[str, float]]:
    task_lower = task_text.lower()
    families = {_infer_web_action_family(action)[0] for action in selected_actions}
    breakdown: dict[str, float] = {}

    def room_average(parameter: str) -> float | None:
        values = [
            after_parameter_scores.get(room, {}).get(parameter)
            for room in WEB_ROOM_KEYS
            if after_parameter_scores.get(room, {}).get(parameter) is not None
        ]
        if not values:
            return None
        return round(sum(values) / len(values), 4)

    explicit = False

    if any(keyword in task_lower for keyword in ("cool", "cooling", "hot", "warm", "temperature")):
        explicit = True
        score = room_average("temperature")
        if score is not None:
            breakdown["temperature"] = score
    if any(keyword in task_lower for keyword in ("humid", "humidity", "dry", "damp", "moist")):
        explicit = True
        score = room_average("humidity")
        if score is not None:
            breakdown["humidity"] = score
    if any(keyword in task_lower for keyword in ("air", "stuffy", "fresh", "ventilate", "ventilation")):
        explicit = True
        score = room_average("air")
        if score is not None:
            breakdown["air"] = score
    if any(keyword in task_lower for keyword in ("light", "bright", "brightness", "dim", "dark")):
        explicit = True
        score = room_average("brightness")
        if score is not None:
            breakdown["brightness"] = score
    if any(keyword in task_lower for keyword in ("quiet", "noise", "sleep", "rest")):
        explicit = True
        score = room_average("noise")
        if score is not None:
            breakdown["noise"] = score
    if any(keyword in task_lower for keyword in ("movie", "video")):
        explicit = True
        brightness = room_average("brightness")
        movie_actions = 1.0 if "computer" in families or "curtain" in families else 0.4
        components = [value for value in [brightness, movie_actions] if value is not None]
        if components:
            breakdown["movie_scene"] = round(sum(components) / len(components), 4)
    if "music" in task_lower:
        explicit = True
        breakdown["music_scene"] = 1.0 if "computer" in families else 0.35

    if not explicit:
        return False, None, breakdown
    if not breakdown:
        return True, 0.0, breakdown
    return True, round(sum(breakdown.values()) / len(breakdown), 4), breakdown


def _score_web_conflicts(
    *,
    actions: list[PlannedAction],
    task_text: str,
    outdoor_state: dict[str, float],
) -> tuple[int, float, float]:
    task_lower = task_text.lower()
    flags = {
        "ac_on": False,
        "window_open": False,
        "dehumidifier_on": False,
        "fresh_air_on": False,
        "fresh_air_high": False,
        "fan_high": False,
        "light_high": False,
        "curtain_open": False,
        "curtain_closed": False,
        "computer_active": False,
        "computer_video": False,
    }

    for action in actions:
        family, _ = _infer_web_action_family(action)
        attr = str(action.attribute).lower()
        value = action.value
        lowered_value = str(value).lower()
        if family == "air_conditioner":
            if (attr == "power" and bool(value)) or attr in {"target_temperature", "mode", "fan_speed"}:
                flags["ac_on"] = True
        elif family == "window" and attr == "position" and lowered_value in {"open", "half"}:
            flags["window_open"] = True
        elif family == "dehumidifier" and ((attr == "power" and bool(value)) or attr in {"target_humidity", "humidity"}):
            flags["dehumidifier_on"] = True
        elif family == "fresh_air":
            if (attr == "power" and bool(value)) or attr in {"flow_level", "mode"}:
                flags["fresh_air_on"] = True
            if lowered_value in {"high", "boost"}:
                flags["fresh_air_high"] = True
        elif family == "fan":
            if lowered_value == "high":
                flags["fan_high"] = True
        elif family == "light":
            if attr == "brightness":
                try:
                    if float(value) >= 70:
                        flags["light_high"] = True
                except (TypeError, ValueError):
                    pass
            elif attr == "power" and bool(value):
                flags["light_high"] = True
        elif family == "curtain" and attr == "position":
            if lowered_value == "open":
                flags["curtain_open"] = True
            elif lowered_value == "closed":
                flags["curtain_closed"] = True
        elif family == "computer":
            if (attr == "power" and bool(value)) or attr in {"playlist", "media_track", "input_source", "volume"}:
                flags["computer_active"] = True
            if attr in {"input_source", "media_track"} or "video" in lowered_value or "movie" in lowered_value:
                flags["computer_video"] = True

    hard_conflict_count = 0
    soft_conflict_cost = 0.0
    synergy_bonus = 0.0

    if flags["ac_on"] and flags["window_open"]:
        hard_conflict_count += 1
    if flags["dehumidifier_on"] and flags["window_open"] and float(outdoor_state.get("humidity", 0.0)) >= 65.0:
        hard_conflict_count += 1
    if "sleep" in task_lower and flags["fresh_air_high"] and flags["fan_high"]:
        hard_conflict_count += 1
    if any(keyword in task_lower for keyword in ("movie", "video")) and flags["light_high"] and flags["curtain_open"]:
        hard_conflict_count += 1
    if flags["window_open"] and float(outdoor_state.get("air", 100.0)) <= 35.0:
        hard_conflict_count += 1

    if flags["fresh_air_on"] and flags["ac_on"]:
        soft_conflict_cost += 0.25
    if flags["fan_high"] and flags["computer_video"]:
        soft_conflict_cost += 0.18
    if flags["curtain_closed"] and flags["light_high"]:
        soft_conflict_cost += 0.12
    if flags["dehumidifier_on"] and flags["ac_on"]:
        soft_conflict_cost += 0.16

    if flags["curtain_closed"] and flags["ac_on"]:
        synergy_bonus += 0.22
    if flags["ac_on"] and any(
        str(action.attribute).lower() == "target_temperature" and 24 <= _safe_float(action.value, 24.0) <= 26
        for action in actions
    ) and any(_infer_web_action_family(action)[0] == "fan" for action in actions):
        synergy_bonus += 0.18
    if flags["fresh_air_on"] and flags["ac_on"] and not flags["window_open"]:
        synergy_bonus += 0.12
    if flags["curtain_closed"] and flags["computer_active"]:
        synergy_bonus += 0.15
    if any(keyword in task_lower for keyword in ("movie", "video")) and not flags["light_high"] and flags["computer_active"]:
        synergy_bonus += 0.10

    return hard_conflict_count, round(soft_conflict_cost, 4), round(synergy_bonus, 4)


def _score_web_action_clarity(actions: list[PlannedAction]) -> float:
    if not actions:
        return 1.0
    clarity_scores: list[float] = []
    for action in actions:
        score = 0.0
        score += 0.2 if str(action.device_id).strip() else 0.0
        score += 0.2 if str(action.attribute).strip() else 0.0
        score += 0.2 if action.value is not None else 0.0
        score += 0.2 if str(action.requested_by).strip() else 0.0
        score += 0.2 if str(action.reason).strip() else 0.0
        clarity_scores.append(score)
    return round(sum(clarity_scores) / len(clarity_scores), 4)


def _build_web_eval_metrics(
    *,
    row: dict[str, Any],
    task_request: TaskRequest,
    result: OrchestrationResult,
) -> WebEvalMetrics | None:
    source_profile = get_dataset_source_profile(str(row.get("source_dataset") or ""))
    if source_profile.source_family != WEB_DATASET_FAMILY:
        return None

    before_state = _extract_web_state(row.get("environment_json"))
    if before_state is None:
        return WebEvalMetrics(evaluated=False)

    after_state = _extract_web_state(result.execution.state_snapshot)
    if after_state is None:
        after_state = _project_web_state_after(before_state, result.plan.selected_actions)

    before_comfort, _, _ = _score_web_state(before_state, task_text=task_request.description)
    after_comfort, room_scores, parameter_scores = _score_web_state(after_state, task_text=task_request.description)
    comfort_improvement = round(after_comfort - before_comfort, 4)

    has_explicit_demand, demand_satisfaction, demand_breakdown = _score_web_demand_satisfaction(
        task_text=task_request.description,
        after_parameter_scores=parameter_scores,
        selected_actions=result.plan.selected_actions,
    )
    hard_conflict_count, soft_conflict_cost, synergy_bonus = _score_web_conflicts(
        actions=result.plan.selected_actions,
        task_text=task_request.description,
        outdoor_state=after_state.get("outdoor", {}),
    )

    before_energy = sum(float(before_state.get(room, {}).get("energy", 0.0)) for room in WEB_ROOM_KEYS)
    after_energy = sum(float(after_state.get(room, {}).get("energy", 0.0)) for room in WEB_ROOM_KEYS)
    energy_cost = round(max(0.0, after_energy - before_energy) / 100.0, 4)
    energy_efficiency = round(comfort_improvement / max(energy_cost, 0.05), 4)
    coordination_score = round(
        _clamp_score(
            1.0
            - (hard_conflict_count * 0.45)
            - (soft_conflict_cost * 0.35)
            - (len(result.conflicts) * 0.05)
            + (synergy_bonus * 0.30)
        ),
        4,
    )
    action_utility = round(
        comfort_improvement
        + synergy_bonus
        - energy_cost
        - soft_conflict_cost
        - (hard_conflict_count * 0.50),
        4,
    )

    return WebEvalMetrics(
        evaluated=True,
        has_explicit_demand=has_explicit_demand,
        comfort_score=after_comfort,
        comfort_improvement=comfort_improvement,
        demand_satisfaction=demand_satisfaction,
        energy_cost=energy_cost,
        energy_efficiency=energy_efficiency,
        hard_conflict_count=hard_conflict_count,
        soft_conflict_cost=soft_conflict_cost,
        synergy_bonus=synergy_bonus,
        coordination_score=coordination_score,
        action_utility=action_utility,
        action_clarity=_score_web_action_clarity(result.plan.selected_actions),
        room_scores_json=room_scores,
        parameter_scores_json=parameter_scores,
        demand_breakdown_json=demand_breakdown,
    )


def _mean_or_none(values: list[float | int | None]) -> float | None:
    filtered = [float(value) for value in values if value is not None]
    if not filtered:
        return None
    return round(sum(filtered) / len(filtered), 6)


def _build_web_summary(records: list[DatasetEvalRecord]) -> WebEvalSummary | None:
    if not records:
        return None
    web_metrics = [record.web_metrics for record in records if record.web_metrics is not None]
    if not web_metrics:
        return None
    evaluated = [metric for metric in web_metrics if metric and metric.evaluated]
    return WebEvalSummary(
        sample_count=len(records),
        evaluated_sample_count=len(evaluated),
        avg_comfort_score=_mean_or_none([metric.comfort_score for metric in evaluated]),
        avg_comfort_improvement=_mean_or_none([metric.comfort_improvement for metric in evaluated]),
        avg_demand_satisfaction=_mean_or_none([metric.demand_satisfaction for metric in evaluated]),
        avg_energy_cost=_mean_or_none([metric.energy_cost for metric in evaluated]),
        avg_energy_efficiency=_mean_or_none([metric.energy_efficiency for metric in evaluated]),
        avg_hard_conflict_count=_mean_or_none([metric.hard_conflict_count for metric in evaluated]),
        avg_soft_conflict_cost=_mean_or_none([metric.soft_conflict_cost for metric in evaluated]),
        avg_synergy_bonus=_mean_or_none([metric.synergy_bonus for metric in evaluated]),
        avg_coordination_score=_mean_or_none([metric.coordination_score for metric in evaluated]),
        avg_action_utility=_mean_or_none([metric.action_utility for metric in evaluated]),
        avg_action_clarity=_mean_or_none([metric.action_clarity for metric in evaluated]),
    )


def _build_summary(records: list[DatasetEvalRecord]) -> DatasetEvalSummary:
    if not records:
        return DatasetEvalSummary(
            sample_count=0,
            execution_success_rate=0.0,
            avg_latency_ms=0.0,
            avg_conflict_count=0.0,
            avg_selected_agent_count=0.0,
            avg_predicted_action_count=0.0,
            avg_gold_action_count=0.0,
            avg_action_count_abs_error=0.0,
            wakeup_agent_f1=0.0,
            proposal_domain_f1=0.0,
            proposal_action_f1=0.0,
            final_domain_f1=0.0,
            final_service_f1=0.0,
            final_action_f1=0.0,
            wakeup_agent_exact_match_rate=0.0,
            final_domain_exact_match_rate=0.0,
            final_action_exact_match_rate=0.0,
        )

    frame = pd.DataFrame([record.model_dump(mode="json") for record in records])
    return DatasetEvalSummary(
        sample_count=len(records),
        execution_success_rate=float(frame["execution_success"].mean()),
        avg_latency_ms=float(frame["latency_ms"].mean()),
        avg_conflict_count=float(frame["conflict_count"].mean()),
        avg_selected_agent_count=float(frame["selected_agent_count"].mean()),
        avg_predicted_action_count=float(frame["predicted_action_count"].mean()),
        avg_gold_action_count=float(frame["gold_action_count"].mean()),
        avg_action_count_abs_error=float(frame["action_count_abs_error"].mean()),
        wakeup_agent_f1=float(frame["wakeup_agent_f1"].mean()),
        proposal_domain_f1=float(frame["proposal_domain_f1"].mean()),
        proposal_action_f1=float(frame["proposal_action_f1"].mean()),
        final_domain_f1=float(frame["final_domain_f1"].mean()),
        final_service_f1=float(frame["final_service_f1"].mean()),
        final_action_f1=float(frame["final_action_f1"].mean()),
        wakeup_agent_exact_match_rate=float(frame["wakeup_agent_exact_match"].mean()),
        final_domain_exact_match_rate=float(frame["final_domain_exact_match"].mean()),
        final_action_exact_match_rate=float(frame["final_action_exact_match"].mean()),
    )


class EpisodeReplayBackend(SimulatorBackend):
    """Replay one warehouse episode state through the current orchestrator."""

    def __init__(self) -> None:
        self.current_state = HomeState(
            sensors=SensorSnapshot(),
            devices=DeviceState(),
            outdoor=OutdoorState(),
        )

    def set_state(self, home_state: HomeState) -> None:
        self.current_state = home_state.model_copy(deep=True)

    def get_home_state(self) -> HomeState:
        return self.current_state.model_copy(deep=True)

    def apply_actions(self, actions: list[PlannedAction]) -> HomeState:
        next_state = self.current_state.model_copy(deep=True)
        for action in actions:
            if action.device_id in next_state.devices.air_conditioners:
                setattr(next_state.devices.air_conditioners[action.device_id], action.attribute, action.value)
            elif action.device_id in next_state.devices.lights:
                setattr(next_state.devices.lights[action.device_id], action.attribute, action.value)
            elif action.device_id == "music_player":
                setattr(next_state.devices.music_player, action.attribute, action.value)
            elif action.device_id in next_state.devices.fans:
                setattr(next_state.devices.fans[action.device_id], action.attribute, action.value)
            elif action.device_id in next_state.devices.covers:
                setattr(next_state.devices.covers[action.device_id], action.attribute, action.value)
            elif action.device_id in next_state.devices.locks:
                setattr(next_state.devices.locks[action.device_id], action.attribute, action.value)
            elif action.device_id in next_state.devices.switches:
                setattr(next_state.devices.switches[action.device_id], action.attribute, action.value)
            elif action.device_id in next_state.devices.appliances:
                setattr(next_state.devices.appliances[action.device_id], action.attribute, action.value)
        self.current_state = next_state
        return self.get_home_state()


@dataclass
class DatasetEvaluationRunner:
    """Offline evaluator that replays warehouse episodes through the current system."""

    central_node: CentralNode
    replay_backend: EpisodeReplayBackend

    @classmethod
    def build(
        cls,
        *,
        output_dir: Path,
        primary_memory_backend: str = "none",
        llm_enabled: bool = False,
    ) -> "DatasetEvaluationRunner":
        settings = build_settings(
            {
                "output_dir": output_dir,
                "primary_memory_backend": primary_memory_backend,
                "llm_enabled": llm_enabled,
            }
        )
        replay_backend = EpisodeReplayBackend()
        simulator = HomeSimulator(backend=replay_backend)
        triple_store = TripleStore(settings.memory_dir)
        workspace_store = WorkspaceMemoryStore(settings.agent_workspace_dir)
        registry = AgentRegistry.from_config(
            settings.agents_config_path,
            workspace_store=workspace_store,
            agent_mode=settings.agent_mode,
            agent_catalog_path=settings.agent_catalog_path,
        )
        memory_coordinator = MemoryCoordinator(
            graph_retriever=GraphRetriever(triple_store),
            workspace_store=workspace_store,
            primary_backend=primary_memory_backend,
        )
        central_node = CentralNode.build_default(
            simulator=simulator,
            agent_registry=registry,
            triple_store=triple_store,
            memory_coordinator=memory_coordinator,
            compression_window=settings.compression_window,
        )
        return cls(central_node=central_node, replay_backend=replay_backend)

    def evaluate_rows(
        self,
        rows: list[dict[str, Any]],
        *,
        show_progress: bool = True,
        progress_desc: str = "Evaluate episodes",
    ) -> list[DatasetEvalRecord]:
        """Evaluate a pre-joined list of episode rows."""

        records: list[DatasetEvalRecord] = []
        iterator = rows
        if show_progress and tqdm is not None:
            iterator = tqdm(rows, desc=progress_desc, total=len(rows), unit="sample", dynamic_ncols=True)
        for row in iterator:
            records.append(self.evaluate_row(row))
        return records

    def evaluate_row(self, row: dict[str, Any]) -> DatasetEvalRecord:
        """Evaluate one joined episode row."""

        state_row = {
            "snapshot_ts": row.get("snapshot_ts"),
            "occupancy_status": row.get("occupancy_status"),
            "sensor_summary_json": row.get("sensor_summary_json"),
            "device_state_json": row.get("device_state_json"),
            "environment_json": row.get("environment_json"),
            "history_action_summary_json": row.get("history_action_summary_json"),
        }
        task_row = {
            "task_id": row.get("task_id"),
            "task_source": row.get("task_source"),
            "raw_text": row.get("raw_text"),
            "parsed_slots_json": row.get("parsed_slots_json"),
            "trigger_json": row.get("trigger_json"),
            "source_dataset": row.get("source_dataset"),
        }
        home_state = build_home_state_from_snapshot(state_row)
        task_request = build_task_request_from_rows(task_row, state_row)
        self.replay_backend.set_state(home_state)

        gold_target_actions = _parse_json_like(row.get("target_actions_json")) or []
        if not isinstance(gold_target_actions, list):
            gold_target_actions = []
        gold_norm = normalize_target_actions(gold_target_actions)
        gold_agents = infer_gold_agents(gold_target_actions, task_request.description)

        started_at = time.perf_counter()
        result = self.central_node.handle_task(task_request)
        latency_ms = (time.perf_counter() - started_at) * 1000.0

        predicted_norm = normalize_predicted_actions(result.plan.selected_actions)
        proposal_actions = self._proposal_actions(result.agent_dialogue)
        proposal_norm = normalize_predicted_actions(proposal_actions)

        agent_precision, agent_recall, agent_f1 = _precision_recall_f1(set(result.selected_agents), gold_agents)
        proposal_domain_precision, proposal_domain_recall, proposal_domain_f1 = _precision_recall_f1(proposal_norm["domains"], gold_norm["domains"])
        proposal_action_precision, proposal_action_recall, proposal_action_f1 = _precision_recall_f1(proposal_norm["actions"], gold_norm["actions"])
        final_domain_precision, final_domain_recall, final_domain_f1 = _precision_recall_f1(predicted_norm["domains"], gold_norm["domains"])
        final_service_precision, final_service_recall, final_service_f1 = _precision_recall_f1(predicted_norm["services"], gold_norm["services"])
        final_action_precision, final_action_recall, final_action_f1 = _precision_recall_f1(predicted_norm["actions"], gold_norm["actions"])
        web_metrics = _build_web_eval_metrics(
            row=row,
            task_request=task_request,
            result=result,
        )

        return DatasetEvalRecord(
            sample_id=str(row["sample_id"]),
            source_dataset=str(row.get("source_dataset") or "unknown"),
            task_source=str(row.get("task_source") or "unknown"),
            label_quality=str(row.get("label_quality") or "unknown"),
            gold_action_count=len(gold_target_actions),
            predicted_action_count=len(result.plan.selected_actions),
            proposal_action_count=len(proposal_actions),
            selected_agent_count=len(result.selected_agents),
            discussion_turn_count=len(result.agent_dialogue),
            conflict_count=len(result.conflicts),
            execution_success=result.execution.success,
            latency_ms=round(latency_ms, 3),
            wakeup_agent_precision=agent_precision,
            wakeup_agent_recall=agent_recall,
            wakeup_agent_f1=agent_f1,
            wakeup_agent_exact_match=set(result.selected_agents) == gold_agents,
            proposal_domain_precision=proposal_domain_precision,
            proposal_domain_recall=proposal_domain_recall,
            proposal_domain_f1=proposal_domain_f1,
            proposal_action_precision=proposal_action_precision,
            proposal_action_recall=proposal_action_recall,
            proposal_action_f1=proposal_action_f1,
            final_domain_precision=final_domain_precision,
            final_domain_recall=final_domain_recall,
            final_domain_f1=final_domain_f1,
            final_service_precision=final_service_precision,
            final_service_recall=final_service_recall,
            final_service_f1=final_service_f1,
            final_action_precision=final_action_precision,
            final_action_recall=final_action_recall,
            final_action_f1=final_action_f1,
            final_domain_exact_match=predicted_norm["domains"] == gold_norm["domains"],
            final_action_exact_match=predicted_norm["actions"] == gold_norm["actions"],
            action_count_abs_error=abs(len(result.plan.selected_actions) - len(gold_target_actions)),
            selected_agents_json=list(result.selected_agents),
            gold_agents_json=sorted(gold_agents),
            predicted_domains_json=sorted(predicted_norm["domains"]),
            gold_domains_json=sorted(gold_norm["domains"]),
            web_metrics=web_metrics,
        )

    @staticmethod
    def _proposal_actions(dialogue: list[AgentDialogueEntry]) -> list[PlannedAction]:
        actions: list[PlannedAction] = []
        for entry in dialogue:
            actions.extend(entry.actions)
        return actions


def load_evaluation_rows(
    *,
    episodes_path: Path,
    states_path: Path,
    tasks_path: Path,
    split: str | None = "test",
    source_datasets: list[str] | None = None,
    label_qualities: list[str] | None = None,
    max_samples: int | None = None,
    sample_per_source: int | None = None,
) -> list[dict[str, Any]]:
    """Load and join episode/state/task rows for offline evaluation."""

    episodes = pd.read_parquet(
        episodes_path,
        columns=[
            "sample_id",
            "state_id",
            "task_id",
            "target_actions_json",
            "label_quality",
            "split",
        ],
    )
    if split:
        episodes = episodes[episodes["split"] == split]

    tasks = pd.read_parquet(
        tasks_path,
        columns=[
            "task_id",
            "task_source",
            "raw_text",
            "parsed_slots_json",
            "trigger_json",
            "source_dataset",
        ],
    )
    states = pd.read_parquet(
        states_path,
        columns=[
            "state_id",
            "snapshot_ts",
            "occupancy_status",
            "sensor_summary_json",
            "device_state_json",
            "environment_json",
            "history_action_summary_json",
        ],
    )

    joined = episodes.merge(tasks, on="task_id", how="left").merge(states, on="state_id", how="left")
    if source_datasets:
        joined = joined[joined["source_dataset"].isin(source_datasets)]
    if label_qualities:
        joined = joined[joined["label_quality"].isin(label_qualities)]

    joined = joined.sort_values(["source_dataset", "sample_id"]).reset_index(drop=True)
    if sample_per_source is not None and sample_per_source > 0 and not joined.empty:
        grouped = []
        for _, group in joined.groupby("source_dataset", sort=True):
            grouped.append(group.head(sample_per_source))
        joined = pd.concat(grouped, ignore_index=True) if grouped else joined.iloc[0:0]
    if max_samples is not None and max_samples > 0:
        joined = joined.head(max_samples)
    return joined.to_dict(orient="records")


def build_dataset_eval_report(
    *,
    rows: list[dict[str, Any]],
    output_dir: Path,
    primary_memory_backend: str,
    llm_enabled: bool,
    show_progress: bool = True,
) -> DatasetEvalReport:
    """Run the offline evaluator and aggregate one report."""

    runner = DatasetEvaluationRunner.build(
        output_dir=output_dir,
        primary_memory_backend=primary_memory_backend,
        llm_enabled=llm_enabled,
    )
    records = runner.evaluate_rows(rows, show_progress=show_progress)
    by_source = defaultdict(list)
    by_task_source = defaultdict(list)
    by_label_quality = defaultdict(list)
    for record in records:
        by_source[record.source_dataset].append(record)
        by_task_source[record.task_source].append(record)
        by_label_quality[record.label_quality].append(record)

    return DatasetEvalReport(
        generated_at=datetime.now().isoformat(),
        config={
            "primary_memory_backend": primary_memory_backend,
            "llm_enabled": llm_enabled,
            "output_dir": str(output_dir),
            "sample_count": len(rows),
        },
        summary=_build_summary(records),
        web_summary=_build_web_summary(records),
        by_source_dataset={key: _build_summary(value) for key, value in by_source.items()},
        by_task_source={key: _build_summary(value) for key, value in by_task_source.items()},
        by_label_quality={key: _build_summary(value) for key, value in by_label_quality.items()},
        web_by_source_dataset={
            key: summary
            for key, value in by_source.items()
            if (summary := _build_web_summary(value)) is not None
        },
        records=records,
    )
