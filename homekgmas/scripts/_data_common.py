"""Shared helpers for dataset download and processing scripts."""

from __future__ import annotations

from collections.abc import Iterator
import csv
import io
import json
import pickle
from pathlib import Path
import re
import shutil
import tarfile
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen
import zipfile

import pandas as pd
import yaml

from app.datahub.io import (
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    METADATA_DIR,
    REPORTS_DIR,
    ensure_data_layout,
    upsert_manifest_entry,
    utc_now_iso,
    write_json,
)
from app.datahub.normalize import (
    flatten_actions,
    maybe_parse_json_string,
    normalize_domain,
    normalize_key,
    normalize_room,
    normalize_service,
    parse_timestamp,
    safe_json,
    text_candidates,
)


def log(message: str) -> None:
    """Print a clear data-pipeline log message."""

    print(f"[data-pipeline] {message}", flush=True)


def raw_dataset_dir(name: str) -> Path:
    """Return the raw directory for one dataset."""

    ensure_data_layout()
    return DATA_RAW_DIR / name


def processed_dataset_dir(name: str) -> Path:
    """Return the processed directory for one dataset."""

    ensure_data_layout()
    path = DATA_PROCESSED_DIR / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def update_manifest(
    *,
    dataset_name: str,
    source_url: str,
    local_path: str | Path,
    license_if_known: str,
    download_method: str,
    status: str,
    notes: str,
) -> None:
    """Write one manifest entry."""

    upsert_manifest_entry(
        {
            "dataset_name": dataset_name,
            "source_url": source_url,
            "local_path": local_path,
            "license_if_known": license_if_known,
            "download_method": download_method,
            "status": status,
            "notes": notes,
            "updated_at": utc_now_iso(),
        }
    )


def download_file(url: str, destination: Path) -> Path:
    """Download a remote file to disk."""

    destination.parent.mkdir(parents=True, exist_ok=True)
    log(f"Downloading {url} -> {destination}")
    with urlopen(url) as response, destination.open("wb") as handle:
        shutil.copyfileobj(response, handle)
    return destination


def extract_archive(archive_path: Path, destination: Path) -> Path:
    """Extract zip or tar archives."""

    destination.mkdir(parents=True, exist_ok=True)
    if archive_path.suffix == ".zip":
        with zipfile.ZipFile(archive_path) as archive:
            archive.extractall(destination)
    elif archive_path.suffix in {".gz", ".tgz", ".tar"} or archive_path.name.endswith(".tar.gz"):
        with tarfile.open(archive_path) as archive:
            archive.extractall(destination)
    else:
        raise ValueError(f"Unsupported archive format: {archive_path}")
    return destination


def write_manual_instructions(dataset_name: str, lines: list[str]) -> None:
    """Persist manual download instructions."""

    path = REPORTS_DIR / "data_gaps.md"
    prefix = "" if not path.exists() else "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}## {dataset_name}\n\n")
        for line in lines:
            handle.write(f"- {line}\n")
        handle.write("\n")


def find_first_existing(root: Path, patterns: list[str]) -> list[Path]:
    """Return sorted paths matching glob patterns."""

    matches: list[Path] = []
    for pattern in patterns:
        matches.extend(root.rglob(pattern))
    return sorted({path for path in matches if path.exists()})


def read_any_table(path: Path) -> pd.DataFrame:
    """Read CSV, TSV, JSONL, JSON, or parquet into a dataframe."""

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".jsonl":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return pd.DataFrame(records)
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        if isinstance(payload, dict):
            return pd.json_normalize(payload)
    raise ValueError(f"Unsupported table format: {path}")


def discover_structured_files(root: Path) -> list[Path]:
    """Discover likely structured data files inside one raw dataset directory."""

    patterns = ["*.json", "*.jsonl", "*.yaml", "*.yml", "*.csv", "*.tsv", "*.parquet", "*.pkl", "*.pickle", "*.txt"]
    return [path for path in find_first_existing(root, patterns) if ".git" not in path.parts]


def parse_structured_file(path: Path) -> Any:
    """Read common structured file types."""

    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    if suffix in {".json", ".jsonl"}:
        if suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if suffix in {".csv", ".tsv"}:
        delimiter = "\t" if suffix == ".tsv" else ","
        with path.open("r", encoding="utf-8") as handle:
            return list(csv.DictReader(handle, delimiter=delimiter))
    if suffix in {".pkl", ".pickle"}:
        with path.open("rb") as handle:
            return pickle.load(handle)
    if suffix == ".txt":
        return path.read_text(encoding="utf-8", errors="ignore")
    return None


def iter_records(payload: Any, *, source_path: str = "") -> Iterator[dict[str, Any]]:
    """Flatten nested JSON/YAML-like objects into record dictionaries."""

    if isinstance(payload, dict):
        normalized = {str(key): maybe_parse_json_string(value) for key, value in payload.items()}
        if normalized:
            yield {"__source_path": source_path, **normalized}
        for key, value in normalized.items():
            if isinstance(value, (dict, list)):
                yield from iter_records(value, source_path=f"{source_path}.{key}" if source_path else key)
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            yield from iter_records(item, source_path=f"{source_path}[{index}]")


def build_action_rows_from_record(record: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract action-like fields from a generic record."""

    action_candidates = [
        record.get("actions"),
        record.get("action"),
        record.get("service_calls"),
        record.get("expected_actions"),
        record.get("calls"),
        record.get("sequence"),
        record.get("target"),
    ]
    for candidate in action_candidates:
        actions = flatten_actions(maybe_parse_json_string(candidate))
        if actions:
            return actions
    return []


def infer_dataset_task_text(record: dict[str, Any]) -> str:
    """Infer a task-like text field from a generic record."""

    text = text_candidates(
        record,
        [
            "raw_text",
            "text",
            "request",
            "instruction",
            "input",
            "prompt",
            "utterance",
            "sentence",
            "command",
            "query",
            "goal",
        ],
    )
    if text:
        return text
    intent = text_candidates(record, ["intent", "domain", "name", "title"])
    if intent:
        return f"Intent: {intent}"
    return ""


def infer_candidate_devices(actions: list[dict[str, Any]], record: dict[str, Any]) -> list[str]:
    """Infer candidate devices from actions or record fields."""

    devices = [action.get("device_id", "") for action in actions if action.get("device_id")]
    for key in ("device_id", "entity_id", "device", "target_device", "entity"):
        value = record.get(key)
        if isinstance(value, str) and value.strip():
            devices.append(value.strip())
    deduped: list[str] = []
    seen: set[str] = set()
    for item in devices:
        if item in seen:
            continue
        deduped.append(item)
        seen.add(item)
    return deduped


def parse_casas_event_line(line: str, home_id: str) -> dict[str, Any] | None:
    """Parse one CASAS event line into a normalized event record."""

    stripped = line.strip()
    if not stripped or stripped.startswith("%"):
        return None
    parts = stripped.split()
    if len(parts) < 4:
        return None
    timestamp = parse_timestamp(f"{parts[0]} {parts[1]}")
    sensor_id = parts[2]
    sensor_value = parts[3]
    activity_hint = " ".join(parts[4:]).strip() or None
    sensor_key = normalize_key(sensor_id)
    room_match = re.match(r"([a-zA-Z_]+)", sensor_key)
    room_guess = normalize_room(room_match.group(1)) if room_match else ""
    event_type = normalize_key(sensor_value)
    return {
        "home_id": home_id,
        "timestamp": timestamp,
        "sensor_id": sensor_id,
        "sensor_value": sensor_value,
        "sensor_type": sensor_key[:1].upper() if sensor_key else "",
        "room_hint": room_guess,
        "event_type": event_type,
        "activity_hint": activity_hint,
    }


def write_metadata_defaults() -> None:
    """Ensure metadata mapping files exist."""

    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    defaults = {
        "device_domain_mapping.json": {
            "domains": ["light", "climate", "fan", "switch", "cover", "media_player", "vacuum", "lock", "sensor", "other"]
        },
        "service_mapping.json": {
            "services": [
                "turn_on",
                "turn_off",
                "toggle",
                "set_temperature",
                "set_humidity",
                "set_brightness",
                "open",
                "close",
                "lock",
                "unlock",
                "play",
                "pause",
                "stop",
                "start",
                "custom",
            ]
        },
        "room_mapping.json": {
            "canonical_rooms": [
                "living_room",
                "bedroom",
                "kitchen",
                "bathroom",
                "office",
                "hallway",
            ]
        },
    }
    for filename, payload in defaults.items():
        path = METADATA_DIR / filename
        if not path.exists():
            write_json(path, payload)
