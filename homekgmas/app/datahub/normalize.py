"""Normalization helpers for devices, actions, rooms, and unified schemas."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
import hashlib
import json
import re
from typing import Any


DEVICE_DOMAIN_SYNONYMS = {
    "light": "light",
    "lights": "light",
    "lamp": "light",
    "lighting": "light",
    "climate": "climate",
    "hvac": "climate",
    "ac": "climate",
    "air_conditioner": "climate",
    "airconditioner": "climate",
    "fan": "fan",
    "switch": "switch",
    "plug": "switch",
    "socket": "switch",
    "cover": "cover",
    "blind": "cover",
    "curtain": "cover",
    "media_player": "media_player",
    "speaker": "media_player",
    "speakers": "media_player",
    "tv": "media_player",
    "television": "media_player",
    "music": "media_player",
    "music_player": "media_player",
    "vacuum": "vacuum",
    "lock": "lock",
    "security": "lock",
    "sensor": "sensor",
}

SERVICE_SYNONYMS = {
    "on": "turn_on",
    "off": "turn_off",
    "turnon": "turn_on",
    "turnoff": "turn_off",
    "enable": "turn_on",
    "disable": "turn_off",
    "toggle": "toggle",
    "settemperature": "set_temperature",
    "temperature": "set_temperature",
    "sethumidity": "set_humidity",
    "humidity": "set_humidity",
    "brightness": "set_brightness",
    "dim": "set_brightness",
    "open": "open",
    "close": "close",
    "lock": "lock",
    "unlock": "unlock",
    "play": "play",
    "pause": "pause",
    "stop": "stop",
    "start": "start",
}

ROOM_SYNONYMS = {
    "living room": "living_room",
    "livingroom": "living_room",
    "客厅": "living_room",
    "bedroom": "bedroom",
    "卧室": "bedroom",
    "kitchen": "kitchen",
    "厨房": "kitchen",
    "bathroom": "bathroom",
    "卫生间": "bathroom",
    "office": "office",
    "study": "office",
    "书房": "office",
    "hallway": "hallway",
    "走廊": "hallway",
}


def stable_id(*parts: Any) -> str:
    """Create a stable short identifier from arbitrary values."""

    joined = "||".join(str(part) for part in parts if str(part))
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def normalize_key(value: Any) -> str:
    """Normalize arbitrary strings into a compact key."""

    lowered = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip().lower())
    return lowered.strip("_")


def normalize_domain(value: Any) -> str:
    """Normalize a device domain into the shared label set."""

    key = normalize_key(value)
    return DEVICE_DOMAIN_SYNONYMS.get(key, "other")


def normalize_service(value: Any) -> str:
    """Normalize an action service into the shared label set."""

    key = normalize_key(value)
    return SERVICE_SYNONYMS.get(key, "custom")


def normalize_room(value: Any) -> str:
    """Normalize a room/area label."""

    text = str(value or "").strip()
    if not text:
        return ""
    key = normalize_key(text.replace("-", " ").replace("_", " "))
    source = ROOM_SYNONYMS.get(text.lower(), ROOM_SYNONYMS.get(key.replace("_", " "), key))
    return source or key


def parse_timestamp(value: Any) -> str | None:
    """Convert common timestamp layouts to ISO-8601 when possible."""

    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    candidates = [
        text,
        text.replace("Z", "+00:00"),
        text.replace("/", "-"),
    ]
    for candidate in candidates:
        try:
            return datetime.fromisoformat(candidate).isoformat()
        except ValueError:
            pass
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%m/%d/%Y %H:%M:%S",
        "%m/%d/%Y %H:%M",
        "%Y%m%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    return None


def infer_time_context(timestamp: str | None) -> dict[str, Any]:
    """Infer time-of-day and day-of-week from a parsed timestamp."""

    if not timestamp:
        return {
            "time_of_day": None,
            "day_of_week": None,
        }
    dt = datetime.fromisoformat(timestamp)
    hour = dt.hour
    if 5 <= hour < 12:
        time_of_day = "morning"
    elif 12 <= hour < 17:
        time_of_day = "afternoon"
    elif 17 <= hour < 22:
        time_of_day = "evening"
    else:
        time_of_day = "night"
    return {
        "time_of_day": time_of_day,
        "day_of_week": dt.strftime("%A").lower(),
    }


def safe_json(value: Any) -> Any:
    """Convert nested values into JSON-serializable objects."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): safe_json(item) for key, item in value.items()}
    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray)):
        return [safe_json(item) for item in value]
    return str(value)


def split_for_id(identifier: str, *, train_cutoff: int = 80, valid_cutoff: int = 90) -> str:
    """Assign a stable split based on a hash bucket."""

    bucket = int(hashlib.md5(identifier.encode("utf-8")).hexdigest(), 16) % 100
    if bucket < train_cutoff:
        return "train"
    if bucket < valid_cutoff:
        return "valid"
    return "test"


def text_candidates(record: dict[str, Any], keys: list[str]) -> str:
    """Return the first non-empty string among several candidate keys."""

    for key in keys:
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def flatten_actions(raw_actions: Any) -> list[dict[str, Any]]:
    """Normalize a variety of action-like structures into a common list."""

    if raw_actions is None:
        return []
    if isinstance(raw_actions, dict):
        raw_actions = [raw_actions]
    normalized: list[dict[str, Any]] = []
    if not isinstance(raw_actions, list):
        return normalized
    for action in raw_actions:
        if isinstance(action, str):
            normalized.append(
                {
                    "device_id": "",
                    "domain": normalize_domain("other"),
                    "service": normalize_service(action),
                    "arguments": {},
                }
            )
            continue
        if not isinstance(action, dict):
            continue
        device_id = str(
            action.get("device_id")
            or action.get("entity_id")
            or action.get("target")
            or action.get("device")
            or ""
        ).strip()
        domain = normalize_domain(action.get("domain") or device_id.split(".", 1)[0] if "." in device_id else "")
        service = normalize_service(
            action.get("service")
            or action.get("action")
            or action.get("name")
            or action.get("command")
            or ""
        )
        arguments = safe_json(
            action.get("arguments")
            or action.get("data")
            or action.get("params")
            or action.get("slots")
            or {}
        )
        normalized.append(
            {
                "device_id": device_id,
                "domain": domain,
                "service": service,
                "arguments": arguments,
            }
        )
    return normalized


def maybe_parse_json_string(value: Any) -> Any:
    """Attempt to parse JSON-like strings."""

    if not isinstance(value, str):
        return value
    text = value.strip()
    if not text or text[0] not in "[{":
        return value
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value
