"""File IO and manifest helpers for the unified smart-home data warehouse."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW_DIR = PROJECT_ROOT / "data_raw"
DATA_STAGING_DIR = PROJECT_ROOT / "data_staging"
DATA_INTERIM_DIR = PROJECT_ROOT / "data_interim"
DATA_PROCESSED_DIR = PROJECT_ROOT / "data_processed"
METADATA_DIR = PROJECT_ROOT / "metadata"
REPORTS_DIR = PROJECT_ROOT / "reports"
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
MANIFEST_PATH = METADATA_DIR / "datasets_manifest.json"
LEGACY_PROJECT_ROOT_NAMES = ("pipekgbot", "homekg-mas")


def utc_now_iso() -> str:
    """Return the current UTC time in ISO format."""

    return datetime.now(timezone.utc).isoformat()


def ensure_data_layout() -> None:
    """Create the expected dataset warehouse directory layout."""

    for path in (
        DATA_RAW_DIR / "home_assistant",
        DATA_RAW_DIR / "smartsense",
        DATA_RAW_DIR / "casas",
        DATA_RAW_DIR / "edgewisepersona",
        DATA_RAW_DIR / "zh_commands",
        DATA_RAW_DIR / "fluent",
        DATA_RAW_DIR / "aras",
        DATA_STAGING_DIR,
        DATA_INTERIM_DIR,
        DATA_PROCESSED_DIR,
        REPORTS_DIR,
        NOTEBOOKS_DIR,
        METADATA_DIR,
    ):
        path.mkdir(parents=True, exist_ok=True)


def read_json(path: Path, default: Any | None = None) -> Any:
    """Read JSON from disk when present."""

    if not path.exists():
        return default
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError:
        return default


def write_json(path: Path, payload: Any) -> None:
    """Write JSON with indentation."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write a JSONL file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False))
            handle.write("\n")


def normalize_manifest_local_path(path_value: str | Path) -> str:
    """Store manifest paths relative to the project root whenever possible."""

    path = Path(path_value).expanduser()
    project_relative = _project_relative_path(path)
    if project_relative is not None:
        return project_relative.as_posix()
    return path.as_posix()


def resolve_manifest_local_path(path_value: str | Path) -> Path:
    """Resolve a manifest path against the current project root when applicable."""

    path = Path(path_value).expanduser()
    project_relative = _project_relative_path(path)
    if project_relative is not None:
        return PROJECT_ROOT / project_relative
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _project_relative_path(path: Path) -> Path | None:
    """Return a project-relative path for current or historical repo locations."""

    if not path.is_absolute():
        return path
    try:
        return path.resolve(strict=False).relative_to(PROJECT_ROOT)
    except ValueError:
        pass

    candidate_project_names = {PROJECT_ROOT.name, *LEGACY_PROJECT_ROOT_NAMES}
    matching_indexes = [index for index, part in enumerate(path.parts) if part in candidate_project_names]
    if not matching_indexes:
        return None

    relative_parts = path.parts[matching_indexes[-1] + 1 :]
    return Path(*relative_parts) if relative_parts else Path(".")


def load_manifest(*, resolve_local_paths: bool = False) -> list[dict[str, Any]]:
    """Load the datasets manifest."""

    payload = read_json(MANIFEST_PATH, default=[])
    if not isinstance(payload, list):
        return []
    if not resolve_local_paths:
        return payload

    resolved_entries: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        entry = dict(item)
        local_path = entry.get("local_path")
        if isinstance(local_path, str) and local_path.strip():
            entry["local_path"] = str(resolve_manifest_local_path(local_path))
        resolved_entries.append(entry)
    return resolved_entries


def upsert_manifest_entry(entry: dict[str, Any]) -> None:
    """Insert or replace one manifest entry by dataset name."""

    ensure_data_layout()
    manifest = load_manifest()
    normalized_entry = dict(entry)
    local_path = normalized_entry.get("local_path")
    if isinstance(local_path, (str, Path)) and str(local_path).strip():
        normalized_entry["local_path"] = normalize_manifest_local_path(local_path)
    dataset_name = str(entry.get("dataset_name", "")).strip()
    updated = False
    for index, item in enumerate(manifest):
        if str(item.get("dataset_name", "")).strip() == dataset_name:
            manifest[index] = normalized_entry
            updated = True
            break
    if not updated:
        manifest.append(normalized_entry)
    write_json(MANIFEST_PATH, manifest)


def dataframe_to_parquet(df: pd.DataFrame, path: Path) -> None:
    """Write a dataframe to parquet with stable defaults."""

    path.parent.mkdir(parents=True, exist_ok=True)
    if df.empty:
        df = pd.DataFrame(columns=df.columns)
    prepared = df.copy()
    for column in prepared.columns:
        if prepared[column].dtype != "object":
            continue
        prepared[column] = prepared[column].map(_normalize_object_for_parquet)
    prepared.to_parquet(path, index=False)


def _normalize_object_for_parquet(value: Any) -> Any:
    """Convert nested Python objects into stable JSON strings for parquet."""

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, (list, tuple, set)):
        return json.dumps(list(value), ensure_ascii=False)
    return value


def dataframe_to_csv(df: pd.DataFrame, path: Path) -> None:
    """Write a dataframe to CSV."""

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def append_markdown_section(path: Path, title: str, lines: list[str]) -> None:
    """Append a markdown section to a report."""

    path.parent.mkdir(parents=True, exist_ok=True)
    prefix = "" if not path.exists() else "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}## {title}\n\n")
        for line in lines:
            handle.write(f"- {line}\n")
        handle.write("\n")
