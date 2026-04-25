"""Build staging, canonical, bridge, and episode tables for the smart-home warehouse."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import pickle
from pathlib import Path
import sys
import threading
import time
import zipfile
from typing import Any

import pandas as pd
import yaml

try:
    from tqdm.auto import tqdm
except ImportError:  # pragma: no cover - optional dependency for CLI visibility
    tqdm = None

from app.datahub.io import (
    DATA_PROCESSED_DIR,
    DATA_RAW_DIR,
    DATA_STAGING_DIR,
    METADATA_DIR,
    REPORTS_DIR,
    dataframe_to_parquet,
    load_manifest,
    utc_now_iso,
    write_json,
)
from app.datahub.normalize import (
    maybe_parse_json_string,
    normalize_domain,
    normalize_room,
    normalize_service,
    split_for_id,
    text_candidates,
)
from app.datahub.warehouse_schema import LABEL_QUALITY_ENUM, TABLE_SPECS


PROGRESS_ENABLED = True
FALLBACK_PROGRESS_LOG_EVERY = 250
HEARTBEAT_INTERVAL_SECONDS = 30.0
DEDUP_SKIP_TABLES = {"stg_casas_event", "stg_casas_activity_label"}
_ACTIVITY_LOCK = threading.Lock()
_CURRENT_ACTIVITY = "bootstrapping"
_CURRENT_ACTIVITY_STARTED_AT = time.monotonic()


def stage_log(message: str) -> None:
    """Emit a flushed timestamped warehouse progress message."""

    timestamp = datetime.now().isoformat(timespec="seconds")
    print(f"[warehouse] {timestamp} | {message}", flush=True)


def set_progress_enabled(enabled: bool) -> None:
    """Globally enable or disable progress bars."""

    global PROGRESS_ENABLED
    PROGRESS_ENABLED = enabled


def set_current_activity(message: str) -> None:
    """Update the current long-running activity for heartbeat logging."""

    global _CURRENT_ACTIVITY, _CURRENT_ACTIVITY_STARTED_AT
    with _ACTIVITY_LOCK:
        _CURRENT_ACTIVITY = message
        _CURRENT_ACTIVITY_STARTED_AT = time.monotonic()
    stage_log(f"Activity -> {message}")


def current_activity_snapshot() -> tuple[str, int]:
    """Return the active work label and elapsed seconds since it began."""

    with _ACTIVITY_LOCK:
        return _CURRENT_ACTIVITY, int(max(0.0, time.monotonic() - _CURRENT_ACTIVITY_STARTED_AT))


@contextmanager
def activity_scope(message: str):
    """Temporarily mark a long-running activity for heartbeat visibility."""

    global _CURRENT_ACTIVITY, _CURRENT_ACTIVITY_STARTED_AT
    with _ACTIVITY_LOCK:
        previous_message = _CURRENT_ACTIVITY
        previous_started_at = _CURRENT_ACTIVITY_STARTED_AT
    set_current_activity(message)
    try:
        yield
    finally:
        with _ACTIVITY_LOCK:
            _CURRENT_ACTIVITY = previous_message
            _CURRENT_ACTIVITY_STARTED_AT = previous_started_at


class WarehouseHeartbeat:
    """Emit periodic heartbeat logs while the warehouse build is running."""

    def __init__(self, interval_seconds: float = HEARTBEAT_INTERVAL_SECONDS) -> None:
        self.interval_seconds = interval_seconds
        self._stop_event = threading.Event()
        self._thread = threading.Thread(target=self._run, name="warehouse-heartbeat", daemon=True)

    def _run(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            activity, elapsed_seconds = current_activity_snapshot()
            stage_log(f"Heartbeat: {activity} (elapsed={elapsed_seconds}s)")

    def __enter__(self) -> "WarehouseHeartbeat":
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self._stop_event.set()
        self._thread.join(timeout=1.0)


def iter_progress(iterable: Any, *, desc: str, total: int | None = None, unit: str = "item", log_every: int = FALLBACK_PROGRESS_LOG_EVERY):
    """Wrap iterables with tqdm when available, otherwise emit periodic logs."""

    use_tqdm = (
        PROGRESS_ENABLED
        and tqdm is not None
        and hasattr(sys.stderr, "isatty")
        and sys.stderr.isatty()
    )
    if use_tqdm:
        return tqdm(iterable, desc=desc, total=total, unit=unit, dynamic_ncols=True)

    def generator():
        count = 0
        stage_log(f"{desc} started" + (f" (total={total})" if total is not None else ""))
        for count, item in enumerate(iterable, start=1):
            if count == 1 or count % log_every == 0 or (total is not None and count == total):
                progress_suffix = f"{count}/{total}" if total is not None else str(count)
                stage_log(f"{desc}: {progress_suffix} {unit}")
            yield item
        if count == 0:
            stage_log(f"{desc}: no {unit}s")
        stage_log(f"{desc} finished")

    return generator()


class HomeAssistantLoader(yaml.SafeLoader):
    """YAML loader that tolerates Home Assistant custom tags such as ``!input``."""


def _construct_any(loader: HomeAssistantLoader, node: yaml.Node) -> Any:
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


HomeAssistantLoader.add_constructor(None, _construct_any)
HomeAssistantLoader.add_multi_constructor("", lambda loader, tag_suffix, node: _construct_any(loader, node))


@dataclass
class WarehouseBundle:
    """All warehouse layers built in-memory before being written to parquet."""

    staging: dict[str, pd.DataFrame]
    canonical: dict[str, pd.DataFrame]
    bridges: dict[str, pd.DataFrame]
    episodes: pd.DataFrame
    context: dict[str, Any]


WAREHOUSE_STAGE_ORDER = [
    "manifest",
    "home_assistant",
    "smartsense",
    "casas",
    "edgewisepersona",
    "zh_commands",
    "canonical",
]
STAGING_STAGE_TABLES = {
    "manifest": ["source_manifest"],
    "home_assistant": [
        "stg_ha_home",
        "stg_ha_area",
        "stg_ha_device",
        "stg_ha_entity",
        "stg_ha_assist_record",
        "stg_ha_automation_record",
    ],
    "smartsense": [
        "stg_smartsense_dict",
        "stg_smartsense_log_action",
        "stg_smartsense_routine_device",
    ],
    "casas": ["stg_casas_event", "stg_casas_activity_label"],
    "edgewisepersona": ["stg_edge_character", "stg_edge_routine", "stg_edge_session"],
    "zh_commands": ["stg_zh_command"],
}
CANONICAL_TABLE_NAMES = [
    "dim_home",
    "dim_area",
    "dim_device",
    "dim_entity",
    "dim_user",
    "fact_state_snapshot",
    "fact_task",
    "fact_action_set",
    "fact_action_item",
]
BRIDGE_TABLE_NAMES = [
    "bridge_state_sensor_event",
    "bridge_task_candidate_device",
    "bridge_episode_source",
    "synthetic_discussion",
]
FINAL_STAGE_ORDER = WAREHOUSE_STAGE_ORDER + ["reports"]


def _stage_index(stage_name: str) -> int:
    if stage_name not in FINAL_STAGE_ORDER:
        raise ValueError(f"Unsupported stage: {stage_name}")
    return FINAL_STAGE_ORDER.index(stage_name)


def _checkpoint_path(table_name: str, staging_root: Path, processed_root: Path) -> Path:
    if table_name == "source_manifest":
        return METADATA_DIR / f"{table_name}.parquet"
    if table_name.startswith("stg_"):
        return staging_root / f"{table_name}.parquet"
    return processed_root / f"{table_name}.parquet"


def _deserialize_checkpoint_df(df: pd.DataFrame) -> pd.DataFrame:
    restored = df.copy()
    for column in restored.columns:
        if restored[column].dtype != "object":
            continue
        restored[column] = restored[column].map(maybe_parse_json_string)
    return restored


def _load_checkpoint_tables(table_names: list[str], staging_root: Path, processed_root: Path) -> tuple[dict[str, pd.DataFrame], list[str]]:
    loaded: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    for table_name in table_names:
        path = _checkpoint_path(table_name, staging_root, processed_root)
        if not path.exists():
            missing.append(table_name)
            continue
        loaded[table_name] = _prepare_table(table_name, _deserialize_checkpoint_df(pd.read_parquet(path)))
    return loaded, missing


def _persist_checkpoint_tables(table_map: dict[str, pd.DataFrame], staging_root: Path, processed_root: Path) -> None:
    for table_name, df in table_map.items():
        path = _checkpoint_path(table_name, staging_root, processed_root)
        stage_log(f"Checkpoint save: {table_name} -> {path} ({len(df)} rows)")
        dataframe_to_parquet(_prepare_table(table_name, df), path)


def _summarize_table_sizes(table_map: dict[str, pd.DataFrame]) -> str:
    return ", ".join(f"{name}={len(df)}" for name, df in sorted(table_map.items()))


def _safe_duplicate_count(df: pd.DataFrame) -> int:
    """Count duplicates even when object columns contain unhashable lists or dicts."""

    if df.empty:
        return 0
    normalized = df.copy()
    for column in normalized.columns:
        if normalized[column].dtype != "object":
            continue
        normalized[column] = normalized[column].map(_normalize_object_for_duplicate_check)
    return int(normalized.duplicated().sum())


def _normalize_object_for_duplicate_check(value: Any) -> Any:
    """Convert nested containers into stable hashable representations."""

    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    if isinstance(value, list):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, set):
        return json.dumps(sorted(value), ensure_ascii=False)
    return value


def _load_all_report_inputs(staging_root: Path, processed_root: Path) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, pd.DataFrame], pd.DataFrame]:
    """Load all checkpoint tables needed to regenerate reports only."""

    staging_tables, staging_missing = _load_checkpoint_tables(
        ["source_manifest", *sum((tables for tables in STAGING_STAGE_TABLES.values()), [])],
        staging_root,
        processed_root,
    )
    canonical_tables, canonical_missing = _load_checkpoint_tables(CANONICAL_TABLE_NAMES, staging_root, processed_root)
    bridge_tables, bridge_missing = _load_checkpoint_tables(BRIDGE_TABLE_NAMES, staging_root, processed_root)
    episode_tables, episode_missing = _load_checkpoint_tables(["episodes"], staging_root, processed_root)
    missing = staging_missing + canonical_missing + bridge_missing + episode_missing
    if missing:
        raise FileNotFoundError(f"Missing checkpoint tables for reports-only resume: {missing}")
    return staging_tables, canonical_tables, bridge_tables, episode_tables["episodes"]


def build_warehouse(
    raw_root: Path | None = None,
    staging_root: Path | None = None,
    processed_root: Path | None = None,
    show_progress: bool = True,
    start_from: str = "manifest",
    stop_after: str | None = None,
) -> WarehouseBundle:
    """Build the entire warehouse from locally available raw and processed data."""

    raw_root = raw_root or DATA_RAW_DIR
    staging_root = staging_root or DATA_STAGING_DIR
    processed_root = processed_root or DATA_PROCESSED_DIR
    set_progress_enabled(show_progress)

    start_index = _stage_index(start_from)
    stop_index = _stage_index(stop_after) if stop_after else None
    if stop_index is not None and stop_index < start_index:
        raise ValueError(f"stop_after={stop_after} must not be earlier than start_from={start_from}")

    stage_log(
        f"Build started: raw_root={raw_root}, staging_root={staging_root}, processed_root={processed_root}, "
        f"start_from={start_from}, stop_after={stop_after or 'final'}"
    )
    set_current_activity("warehouse startup")

    staging_tables: dict[str, pd.DataFrame] = {}

    stage_builders = {
        "manifest": lambda: {"source_manifest": build_source_manifest(raw_root)},
        "home_assistant": lambda: stage_home_assistant(raw_root / "home_assistant"),
        "smartsense": lambda: stage_smartsense(raw_root / "smartsense"),
        "casas": lambda: stage_casas(raw_root / "casas"),
        "edgewisepersona": lambda: stage_edgewisepersona(raw_root / "edgewisepersona"),
        "zh_commands": lambda: stage_zh_commands(raw_root / "zh_commands"),
    }

    if start_from == "reports":
        with WarehouseHeartbeat():
            set_current_activity("reports-only resume")
            stage_log("Reports-only resume: loading checkpoint tables")
            staging_tables, canonical_tables, bridge_tables, episodes = _load_all_report_inputs(staging_root, processed_root)
            set_current_activity("writing reports")
            stage_log("Writing reports")
            write_warehouse_reports(raw_root, staging_tables, canonical_tables, bridge_tables, episodes)
            stage_log("Reports-only resume finished successfully")
        return WarehouseBundle(
            staging=staging_tables,
            canonical=canonical_tables,
            bridges=bridge_tables,
            episodes=episodes,
            context={},
        )

    with WarehouseHeartbeat():
        for stage_name in WAREHOUSE_STAGE_ORDER[:6]:
            table_names = STAGING_STAGE_TABLES[stage_name]
            stage_idx = _stage_index(stage_name)
            should_rebuild = stage_idx >= start_index
            if should_rebuild:
                set_current_activity(f"building stage {stage_name}")
                stage_log(f"Building stage {stage_name}")
                stage_tables = stage_builders[stage_name]()
                stage_log(f"Stage {stage_name} complete: {_summarize_table_sizes(stage_tables)}")
                set_current_activity(f"checkpoint save for stage {stage_name}")
                _persist_checkpoint_tables(stage_tables, staging_root, processed_root)
            else:
                set_current_activity(f"loading checkpoint stage {stage_name}")
                stage_tables, missing = _load_checkpoint_tables(table_names, staging_root, processed_root)
                if missing:
                    stage_log(f"Checkpoint miss for stage {stage_name}: {missing}; rebuilding this stage.")
                    set_current_activity(f"rebuilding stage {stage_name}")
                    stage_tables = stage_builders[stage_name]()
                    stage_log(f"Stage {stage_name} rebuilt: {_summarize_table_sizes(stage_tables)}")
                    set_current_activity(f"checkpoint save for rebuilt stage {stage_name}")
                    _persist_checkpoint_tables(stage_tables, staging_root, processed_root)
                else:
                    stage_log(f"Loaded stage {stage_name} from checkpoints: {_summarize_table_sizes(stage_tables)}")
            staging_tables.update(stage_tables)
            if stop_index is not None and stage_idx == stop_index:
                stage_log(f"Stopping after stage {stage_name} as requested.")
                return WarehouseBundle(
                    staging=staging_tables,
                    canonical={},
                    bridges={},
                    episodes=pd.DataFrame(columns=TABLE_SPECS["episodes"].columns),
                    context={},
                )

        stage_log("Staging complete: " + _summarize_table_sizes(staging_tables))

        set_current_activity("building canonical tables and bridges")
        stage_log("Building canonical tables and bridges")
        canonical_tables, bridge_tables, context = build_canonical_and_bridges(staging_tables)
        stage_log("Canonical complete: " + _summarize_table_sizes(canonical_tables))
        stage_log("Bridge complete: " + _summarize_table_sizes(bridge_tables))
        set_current_activity("saving canonical and bridge checkpoints")
        _persist_checkpoint_tables(canonical_tables, staging_root, processed_root)
        _persist_checkpoint_tables(bridge_tables, staging_root, processed_root)
        if stop_after == "canonical":
            stage_log("Stopping after canonical stage as requested.")
            return WarehouseBundle(
                staging=staging_tables,
                canonical=canonical_tables,
                bridges=bridge_tables,
                episodes=pd.DataFrame(columns=TABLE_SPECS["episodes"].columns),
                context=context,
            )

        set_current_activity("building episodes")
        stage_log("Building episodes")
        episodes = build_episodes(canonical_tables, bridge_tables, context)
        stage_log(f"Episodes complete: {len(episodes)} rows")
        set_current_activity("saving episode checkpoints")
        _persist_checkpoint_tables({"episodes": episodes}, staging_root, processed_root)

        set_current_activity("writing parquet outputs")
        stage_log("Writing parquet outputs")
        write_warehouse_tables(staging_root, staging_tables, processed_root, canonical_tables, bridge_tables, episodes)
        set_current_activity("writing reports")
        stage_log("Writing reports")
        write_warehouse_reports(raw_root, staging_tables, canonical_tables, bridge_tables, episodes)
        stage_log("Build finished successfully")

    return WarehouseBundle(
        staging=staging_tables,
        canonical=canonical_tables,
        bridges=bridge_tables,
        episodes=episodes,
        context=context,
    )


def write_warehouse_tables(
    staging_root: Path,
    staging_tables: dict[str, pd.DataFrame],
    processed_root: Path,
    canonical_tables: dict[str, pd.DataFrame],
    bridge_tables: dict[str, pd.DataFrame],
    episodes: pd.DataFrame,
) -> None:
    """Persist warehouse tables to their staging and processed locations."""

    staging_root.mkdir(parents=True, exist_ok=True)
    processed_root.mkdir(parents=True, exist_ok=True)
    for table_name, df in iter_progress(staging_tables.items(), desc="Write staging tables", total=len(staging_tables), unit="table", log_every=1):
        target_root = METADATA_DIR if table_name == "source_manifest" else staging_root
        path = target_root / f"{table_name}.parquet"
        stage_log(f"Writing staging table {table_name} -> {path} ({len(df)} rows)")
        dataframe_to_parquet(_prepare_table(table_name, df), path)
    for table_name, df in iter_progress(canonical_tables.items(), desc="Write canonical tables", total=len(canonical_tables), unit="table", log_every=1):
        path = processed_root / f"{table_name}.parquet"
        stage_log(f"Writing canonical table {table_name} -> {path} ({len(df)} rows)")
        dataframe_to_parquet(_prepare_table(table_name, df), path)
    for table_name, df in iter_progress(bridge_tables.items(), desc="Write bridge tables", total=len(bridge_tables), unit="table", log_every=1):
        path = processed_root / f"{table_name}.parquet"
        stage_log(f"Writing bridge table {table_name} -> {path} ({len(df)} rows)")
        dataframe_to_parquet(_prepare_table(table_name, df), path)
    stage_log(f"Writing final episodes table ({len(episodes)} rows)")
    dataframe_to_parquet(_prepare_table("episodes", episodes), processed_root / "episodes.parquet")


def write_warehouse_reports(
    raw_root: Path,
    staging_tables: dict[str, pd.DataFrame],
    canonical_tables: dict[str, pd.DataFrame],
    bridge_tables: dict[str, pd.DataFrame],
    episodes: pd.DataFrame,
) -> None:
    """Write profile, gap, and quality reports for the warehouse."""

    raw_counts = {
        dataset_dir.name: sum(1 for _ in dataset_dir.rglob("*") if _.is_file())
        for dataset_dir in raw_root.iterdir()
        if dataset_dir.is_dir()
    }
    label_counts = episodes["label_quality"].value_counts(dropna=False).to_dict() if not episodes.empty else {}
    split_counts = episodes["split"].value_counts(dropna=False).to_dict() if not episodes.empty else {}

    lines = ["# Data Profile", ""]
    lines.append("## Raw Files")
    lines.extend([f"- {name}: {count}" for name, count in sorted(raw_counts.items())])
    lines.append("")
    lines.append("## Staging Tables")
    lines.extend([f"- {name}: {len(df)} rows" for name, df in sorted(staging_tables.items())])
    lines.append("")
    lines.append("## Canonical Tables")
    lines.extend([f"- {name}: {len(df)} rows" for name, df in sorted(canonical_tables.items())])
    lines.append("")
    lines.append("## Bridge Tables")
    lines.extend([f"- {name}: {len(df)} rows" for name, df in sorted(bridge_tables.items())])
    lines.append("")
    lines.append("## Episodes")
    lines.append(f"- episodes: {len(episodes)} rows")
    lines.append("- label_quality counts: " + json.dumps(label_counts, ensure_ascii=False))
    lines.append("- split counts: " + json.dumps(split_counts, ensure_ascii=False))
    (REPORTS_DIR / "data_profile.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    gap_lines = [
        "# Data Gaps",
        "",
        "- CASAS and ARAS mainly provide environment observations, not strong appliance action labels.",
        "- SmartSense routine rows often lack explicit service labels, so routine-driven supervision remains weak.",
        "- EdgeWisePersona homes and devices are partly synthetic because the dataset is persona-centered.",
        "- `synthetic_discussion` is generated by rules and explicitly marked synthetic.",
        "- `jc132/Home-Assistant-Requests-Zh` may still require manual confirmation when the Hugging Face repo is unavailable.",
    ]
    (REPORTS_DIR / "data_gaps.md").write_text("\n".join(gap_lines) + "\n", encoding="utf-8")

    quality = {
        "generated_at": utc_now_iso(),
        "staging_counts": {name: int(len(df)) for name, df in staging_tables.items()},
        "canonical_counts": {name: int(len(df)) for name, df in canonical_tables.items()},
        "bridge_counts": {name: int(len(df)) for name, df in bridge_tables.items()},
        "episode_count": int(len(episodes)),
        "label_quality_counts": {key: int(value) for key, value in label_counts.items()},
        "split_counts": {key: int(value) for key, value in split_counts.items()},
        "timestamp_parse_rate": estimate_timestamp_parse_rate(staging_tables, canonical_tables),
        "null_ratio": estimate_null_ratio(canonical_tables, episodes),
        "device_domain_mapping_coverage": estimate_device_coverage(canonical_tables.get("dim_device", pd.DataFrame())),
        "action_mapping_coverage": estimate_action_coverage(canonical_tables.get("fact_action_item", pd.DataFrame())),
        "duplicate_stats": {
            name: _safe_duplicate_count(df) for name, df in {**staging_tables, **canonical_tables, **bridge_tables}.items()
        },
        "split_leakage": estimate_split_leakage(episodes),
    }
    write_json(REPORTS_DIR / "data_quality.json", quality)


def build_source_manifest(raw_root: Path) -> pd.DataFrame:
    """Build a source manifest over files already present under ``data_raw``."""

    manifest_entries = load_dataset_manifest()
    manifest_lookup = {entry.get("dataset_name"): entry for entry in manifest_entries}
    rows: list[dict[str, Any]] = []
    dataset_dirs = sorted(path for path in raw_root.iterdir() if path.is_dir())
    for dataset_dir in iter_progress(dataset_dirs, desc="Manifest datasets", total=len(dataset_dirs), unit="dataset", log_every=1):
        dataset_name = dataset_dir.name
        dataset_entry = manifest_lookup.get(dataset_name) or manifest_lookup.get(dataset_name.rstrip("_datasets"))
        file_paths = sorted(path for path in dataset_dir.rglob("*") if path.is_file())
        stage_log(f"Manifest dataset {dataset_name}: {len(file_paths)} files")
        if not file_paths:
            rows.append(
                {
                    "source_dataset": dataset_name,
                    "source_subdataset": "",
                    "source_path": str(dataset_dir),
                    "file_name": "",
                    "file_format": "",
                    "download_method": (dataset_entry or {}).get("download_method", "unknown"),
                    "license": (dataset_entry or {}).get("license_if_known", "Unknown"),
                    "sha256": "",
                    "ingest_time": utc_now_iso(),
                    "status": (dataset_entry or {}).get("status", "manual"),
                    "notes": (dataset_entry or {}).get("notes", "No files discovered."),
                }
            )
            continue
        for file_path in iter_progress(file_paths, desc=f"Manifest files [{dataset_name}]", total=len(file_paths), unit="file"): 
            rows.append(
                {
                    "source_dataset": dataset_name,
                    "source_subdataset": file_path.parent.name if file_path.parent != dataset_dir else "",
                    "source_path": str(file_path.parent),
                    "file_name": file_path.name,
                    "file_format": file_path.suffix.lower().lstrip("."),
                    "download_method": (dataset_entry or {}).get("download_method", "local"),
                    "license": (dataset_entry or {}).get("license_if_known", "Unknown"),
                    "sha256": sha256_of_file(file_path),
                    "ingest_time": utc_now_iso(),
                    "status": (dataset_entry or {}).get("status", "success"),
                    "notes": (dataset_entry or {}).get("notes", ""),
                }
            )
    return pd.DataFrame(rows)


def stage_home_assistant(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Parse Home Assistant datasets into staging tables."""

    repo_roots = sorted(path.parent for path in raw_dir.rglob("datasets") if path.is_dir())
    home_rows: list[dict[str, Any]] = []
    area_rows: list[dict[str, Any]] = []
    device_rows: list[dict[str, Any]] = []
    entity_rows: list[dict[str, Any]] = []
    assist_rows: list[dict[str, Any]] = []
    automation_rows: list[dict[str, Any]] = []

    for repo_root in iter_progress(repo_roots, desc="Stage HA repos", total=len(repo_roots), unit="repo", log_every=1):
        stage_log(f"Home Assistant repo root: {repo_root}")
        for devices_dir in [repo_root / "datasets" / "devices-v3", repo_root / "datasets" / "devices-v2", repo_root / "datasets" / "devices"]:
            if not devices_dir.exists():
                continue
            device_yaml_paths = sorted(devices_dir.glob("*.yaml"))
            for yaml_path in iter_progress(device_yaml_paths, desc=f"Stage HA devices [{devices_dir.name}]", total=len(device_yaml_paths), unit="yaml"): 
                payload = load_ha_yaml(yaml_path)
                if not isinstance(payload, dict):
                    continue
                ha_home_id = yaml_path.stem
                home_rows.append(
                    {
                        "ha_home_id": ha_home_id,
                        "home_name": payload.get("name") or ha_home_id,
                        "country_code": payload.get("country_code"),
                        "location_desc": payload.get("location"),
                        "home_type": payload.get("type"),
                        "amenities_json": payload.get("amenities") or [],
                        "source_file": str(yaml_path.relative_to(repo_root)),
                    }
                )
                devices_by_area = payload.get("devices") or {}
                for area_order, area_name in enumerate(devices_by_area.keys()):
                    area_rows.append(
                        {
                            "ha_home_id": ha_home_id,
                            "area_name": area_name,
                            "area_order": area_order,
                            "source_file": str(yaml_path.relative_to(repo_root)),
                        }
                    )
                    for device in devices_by_area.get(area_name) or []:
                        if not isinstance(device, dict):
                            continue
                        device_name = str(device.get("name") or "").strip()
                        domain = device.get("device_type") or device.get("type")
                        device_rows.append(
                            {
                                "ha_home_id": ha_home_id,
                                "area_name": area_name,
                                "device_name": device_name,
                                "device_type_raw": domain,
                                "model_raw": device.get("model"),
                                "manufacturer_raw": device.get("manufacturer"),
                                "source_file": str(yaml_path.relative_to(repo_root)),
                            }
                        )
                        entity_id = f"{normalize_domain(domain)}.{normalize_text(device_name)}" if device_name else ""
                        entity_rows.append(
                            {
                                "ha_home_id": ha_home_id,
                                "area_name": area_name,
                                "device_name": device_name,
                                "entity_id": entity_id,
                                "entity_domain": normalize_domain(domain),
                                "source_file": str(yaml_path.relative_to(repo_root)),
                            }
                        )
        for assist_root_name in ["assist", "assist-mini"]:
            assist_root = repo_root / "datasets" / assist_root_name
            if not assist_root.exists():
                continue
            assist_yaml_paths = sorted(assist_root.rglob("*.yaml"))
            for yaml_path in iter_progress(assist_yaml_paths, desc=f"Stage HA {assist_root_name}", total=len(assist_yaml_paths), unit="yaml"): 
                if yaml_path.name.startswith("_") or yaml_path.name == "dataset_card.yaml":
                    continue
                payload = load_ha_yaml(yaml_path)
                if not isinstance(payload, dict):
                    continue
                for test_index, test in enumerate(payload.get("tests", []) or []):
                    if not isinstance(test, dict):
                        continue
                    assist_rows.append(
                        {
                            "ha_record_id": f"{assist_root_name}:{yaml_path.stem}:{test_index}",
                            "dataset_name": assist_root_name,
                            "category": payload.get("category"),
                            "sentence_list_json": test.get("sentences") or [],
                            "setup_json": test.get("setup") or {},
                            "expect_changes_json": test.get("expect_changes") or {},
                            "ignore_changes_json": test.get("ignore_changes") or {},
                            "fixture_home_ref": yaml_path.parent.name,
                            "source_file": str(yaml_path.relative_to(repo_root)),
                        }
                    )
                    fixture_payload = load_ha_yaml(yaml_path.parent / "_fixtures.yaml") if (yaml_path.parent / "_fixtures.yaml").exists() else {}
                    for entity in (fixture_payload or {}).get("entities", []) if isinstance(fixture_payload, dict) else []:
                        if not isinstance(entity, dict):
                            continue
                        entity_rows.append(
                            {
                                "ha_home_id": yaml_path.parent.name,
                                "area_name": entity.get("area") or entity.get("area_id") or "",
                                "device_name": entity.get("device_name") or entity.get("name") or entity.get("entity_id"),
                                "entity_id": entity.get("entity_id"),
                                "entity_domain": normalize_domain(str(entity.get("entity_id", "")).split(".", 1)[0]),
                                "source_file": str((yaml_path.parent / "_fixtures.yaml").relative_to(repo_root)),
                            }
                        )
        automation_root = repo_root / "datasets" / "automations"
        if automation_root.exists():
            automation_dirs = sorted(path for path in automation_root.iterdir() if path.is_dir())
            for folder in iter_progress(automation_dirs, desc="Stage HA automations", total=len(automation_dirs), unit="automation", log_every=1):
                description = (folder / "DESCRIPTION.md").read_text(encoding="utf-8").strip() if (folder / "DESCRIPTION.md").exists() else folder.name
                solution = load_ha_yaml(folder / "solution.yaml") if (folder / "solution.yaml").exists() else {}
                automation_rows.append(
                    {
                        "automation_id": folder.name,
                        "problem_readme": description,
                        "expected_result_json": solution,
                        "test_logic_ref": "solution.yaml",
                        "fixture_home_ref": folder.name,
                        "source_file": str(folder.relative_to(repo_root)),
                    }
                )
    return {
        "stg_ha_home": dedupe_for_spec("stg_ha_home", pd.DataFrame(home_rows)),
        "stg_ha_area": dedupe_for_spec("stg_ha_area", pd.DataFrame(area_rows)),
        "stg_ha_device": dedupe_for_spec("stg_ha_device", pd.DataFrame(device_rows)),
        "stg_ha_entity": dedupe_for_spec("stg_ha_entity", pd.DataFrame(entity_rows)),
        "stg_ha_assist_record": dedupe_for_spec("stg_ha_assist_record", pd.DataFrame(assist_rows)),
        "stg_ha_automation_record": dedupe_for_spec("stg_ha_automation_record", pd.DataFrame(automation_rows)),
    }


def stage_smartsense(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Parse SmartSense logs, routines, and dictionaries into staging tables."""

    archive_candidates = sorted(path for path in raw_dir.rglob("data.zip"))
    if not archive_candidates:
        return {
            "stg_smartsense_dict": pd.DataFrame(columns=TABLE_SPECS["stg_smartsense_dict"].columns),
            "stg_smartsense_log_action": pd.DataFrame(columns=TABLE_SPECS["stg_smartsense_log_action"].columns),
            "stg_smartsense_routine_device": pd.DataFrame(columns=TABLE_SPECS["stg_smartsense_routine_device"].columns),
        }
    archive_path = archive_candidates[0]
    dict_rows: list[dict[str, Any]] = []
    log_rows: list[dict[str, Any]] = []
    routine_rows: list[dict[str, Any]] = []

    with zipfile.ZipFile(archive_path) as archive:
        regions = sorted({name.split("/", 1)[0] for name in archive.namelist() if "/" in name})
        for region in iter_progress(regions, desc="Stage SmartSense regions", total=len(regions), unit="region", log_every=1):
            stage_log(f"SmartSense region {region}")
            dictionary_source = archive.read(f"{region}/dictionary.py").decode("utf-8")
            namespace: dict[str, Any] = {}
            exec(dictionary_source, {}, namespace)
            for dict_type, mapping in namespace.items():
                if not isinstance(mapping, dict):
                    continue
                for raw_name, raw_id in mapping.items():
                    dict_rows.append(
                        {
                            "region_or_country": region,
                            "dict_type": dict_type,
                            "raw_id": int(raw_id),
                            "raw_name": raw_name,
                        }
                    )
            for split_name, split_file in [("train", "trn_instance_10.pkl"), ("valid", "vld_instance_10.pkl"), ("test", "test_instance_10.pkl")]:
                if f"{region}/{split_file}" not in archive.namelist():
                    continue
                instances = pickle.loads(archive.read(f"{region}/{split_file}"))
                stage_log(f"SmartSense {region}/{split_name}: {len(instances)} instances")
                for instance_index, sequence in enumerate(iter_progress(instances, desc=f"Stage SmartSense {region}/{split_name}", total=len(instances), unit="instance")):
                    log_instance_id = f"{region}:{split_name}:{instance_index}"
                    for step_index, step in enumerate(sequence):
                        values = [int(value) for value in list(step)]
                        if len(values) < 5:
                            continue
                        log_rows.append(
                            {
                                "log_instance_id": log_instance_id,
                                "step_index": step_index,
                                "region_or_country": region,
                                "day_of_week_id": values[0],
                                "hour_id": values[1],
                                "device_id_raw": values[2],
                                "control_id_raw": values[3],
                                "device_control_id_raw": values[4],
                                "split": split_name,
                                "source_file": f"{region}/{split_file}",
                            }
                        )
            if f"{region}/routine_device_corpus.txt" in archive.namelist():
                lines = archive.read(f"{region}/routine_device_corpus.txt").decode("utf-8").splitlines()
                for routine_index, line in enumerate(lines):
                    raw_ids = [token for token in line.split() if token.strip()]
                    for sequence_index, raw_id in enumerate(raw_ids):
                        routine_rows.append(
                            {
                                "routine_id": f"{region}:{routine_index}",
                                "region_or_country": region,
                                "sequence_index": sequence_index,
                                "device_id_raw": int(raw_id),
                                "source_file": f"{region}/routine_device_corpus.txt",
                            }
                        )
    return {
        "stg_smartsense_dict": dedupe_for_spec("stg_smartsense_dict", pd.DataFrame(dict_rows)),
        "stg_smartsense_log_action": dedupe_for_spec("stg_smartsense_log_action", pd.DataFrame(log_rows)),
        "stg_smartsense_routine_device": dedupe_for_spec("stg_smartsense_routine_device", pd.DataFrame(routine_rows)),
    }


def stage_casas(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Parse CASAS event streams and interval activity labels into staging tables."""

    event_rows: list[dict[str, Any]] = []
    label_rows: list[dict[str, Any]] = []
    active_ranges: dict[tuple[str, str], list[datetime]] = defaultdict(list)

    casas_files = sorted(raw_dir.rglob("*.csv"))
    total_files = len(casas_files)
    stage_log(f"Stage CASAS discovered {total_files} files under {raw_dir}")
    for file_index, file_path in enumerate(
        iter_progress(casas_files, desc="Stage CASAS files", total=total_files, unit="file", log_every=1),
        start=1,
    ):
        home_id = file_path.stem
        source_file = str(file_path.relative_to(raw_dir))
        file_event_rows = 0
        file_label_rows_start = len(label_rows)
        stage_log(
            f"Stage CASAS file {file_index}/{total_files}: {source_file} size_bytes={file_path.stat().st_size}"
        )
        for row_index, row in enumerate(iter_casas_rows(file_path), start=1):
            if row_index == 1 or row_index % 50000 == 0:
                stage_log(
                    f"Stage CASAS row progress [{source_file}]: row={row_index} events_added={file_event_rows} labels_added={len(label_rows) - file_label_rows_start}"
                )
            event_ts = parse_datetime(row[0], row[1])
            if event_ts is None:
                continue
            sensor_id = row[2]
            message = row[3]
            activity = row[4]
            event_rows.append(
                {
                    "casas_home_id": home_id,
                    "event_ts": event_ts.isoformat(),
                    "sensor_id_raw": sensor_id,
                    "message_raw": message,
                    "sensor_room_hint": normalize_room(sensor_id),
                    "sensor_type_hint": infer_casas_sensor_type(sensor_id, message),
                    "source_file": source_file,
                }
            )
            file_event_rows += 1
            if not activity:
                continue
            label, phase = parse_casas_activity(activity)
            if not label:
                continue
            key = (home_id, label)
            if phase == "begin":
                active_ranges[key].append(event_ts)
            elif phase == "end" and active_ranges[key]:
                start_ts = active_ranges[key].pop()
                label_rows.append(
                    {
                        "casas_home_id": home_id,
                        "start_ts": start_ts.isoformat(),
                        "end_ts": event_ts.isoformat(),
                        "activity_label_raw": label,
                        "source_file": source_file,
                    }
                )
            else:
                label_rows.append(
                    {
                        "casas_home_id": home_id,
                        "start_ts": event_ts.isoformat(),
                        "end_ts": event_ts.isoformat(),
                        "activity_label_raw": label,
                        "source_file": source_file,
                    }
                )
        stage_log(
            f"Finished CASAS file {file_index}/{total_files}: {source_file} events_added={file_event_rows} labels_added={len(label_rows) - file_label_rows_start}"
        )
    stage_log(
        f"Stage CASAS finalize: raw event_rows={len(event_rows)} raw label_rows={len(label_rows)}"
    )
    set_current_activity("stage casas finalize: build event dataframe")
    stage_log("Stage CASAS finalize: building event dataframe")
    event_df = pd.DataFrame.from_records(
        event_rows,
        columns=TABLE_SPECS["stg_casas_event"].columns,
    )
    stage_log(
        f"Stage CASAS finalize: event dataframe ready rows={len(event_df)} columns={len(event_df.columns)}"
    )
    set_current_activity("stage casas finalize: dedupe event dataframe")
    stage_log("Stage CASAS finalize: deduping event dataframe")
    event_df = dedupe_for_spec("stg_casas_event", event_df)
    stage_log(f"Stage CASAS finalize: deduped event rows={len(event_df)}")

    set_current_activity("stage casas finalize: build label dataframe")
    stage_log("Stage CASAS finalize: building label dataframe")
    label_df = pd.DataFrame.from_records(
        label_rows,
        columns=TABLE_SPECS["stg_casas_activity_label"].columns,
    )
    stage_log(
        f"Stage CASAS finalize: label dataframe ready rows={len(label_df)} columns={len(label_df.columns)}"
    )
    set_current_activity("stage casas finalize: dedupe label dataframe")
    stage_log("Stage CASAS finalize: deduping label dataframe")
    label_df = dedupe_for_spec("stg_casas_activity_label", label_df)
    stage_log(f"Stage CASAS finalize: deduped label rows={len(label_df)}")

    return {
        "stg_casas_event": event_df,
        "stg_casas_activity_label": label_df,
    }


def stage_edgewisepersona(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Parse EdgeWisePersona raw JSONL files into staging tables."""

    character_rows: list[dict[str, Any]] = []
    routine_rows: list[dict[str, Any]] = []
    session_rows: list[dict[str, Any]] = []

    dataset_dirs = sorted(path for path in raw_dir.iterdir() if path.is_dir())
    for dataset_dir in iter_progress(dataset_dirs, desc="Stage EdgeWisePersona dirs", total=len(dataset_dirs), unit="dir", log_every=1):
        jsonl_paths = sorted(dataset_dir.rglob("*.jsonl"))
        for file_path in iter_progress(jsonl_paths, desc=f"Stage EdgeWisePersona [{dataset_dir.name}]", total=len(jsonl_paths), unit="file", log_every=1):
            lines = [json.loads(line) for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            if "character" in file_path.name:
                for index, item in enumerate(lines):
                    character_rows.append(
                        {
                            "persona_id": f"persona_{index}",
                            "persona_json": item.get("character"),
                            "source_file": str(file_path.relative_to(raw_dir)),
                        }
                    )
            elif "routine" in file_path.name:
                for persona_index, item in enumerate(lines):
                    for routine_index, routine in enumerate(item.get("routines", []) or []):
                        routine_rows.append(
                            {
                                "persona_id": f"persona_{persona_index}",
                                "routine_id": f"routine_{persona_index}_{routine_index}",
                                "trigger_json": routine.get("triggers") or {},
                                "action_json": routine.get("actions") or {},
                                "routine_text": routine_to_text(routine),
                                "source_file": str(file_path.relative_to(raw_dir)),
                            }
                        )
            elif "session" in file_path.name:
                for persona_index, item in enumerate(lines):
                    for session in item.get("sessions", []) or []:
                        session_rows.append(
                            {
                                "persona_id": f"persona_{persona_index}",
                                "session_id": f"session_{persona_index}_{session.get('session_id')}",
                                "session_type": "dialogue",
                                "dialogue_json": session.get("messages") or [],
                                "ground_truth_routine_ids_json": session.get("applied_routines") or [],
                                "source_file": str(file_path.relative_to(raw_dir)),
                            }
                        )
    return {
        "stg_edge_character": dedupe_for_spec("stg_edge_character", pd.DataFrame(character_rows)),
        "stg_edge_routine": dedupe_for_spec("stg_edge_routine", pd.DataFrame(routine_rows)),
        "stg_edge_session": dedupe_for_spec("stg_edge_session", pd.DataFrame(session_rows)),
    }


def stage_zh_commands(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Parse Chinese smart-home command corpora into one staging table."""

    rows: list[dict[str, Any]] = []
    dataset_dirs = sorted(path for path in raw_dir.iterdir() if path.is_dir())
    for dataset_dir in iter_progress(dataset_dirs, desc="Stage zh dirs", total=len(dataset_dirs), unit="dir", log_every=1):
        dataset_name = dataset_dir.name
        candidate_files = sorted(path for path in dataset_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".csv", ".parquet", ".jsonl", ".json"})
        for file_path in iter_progress(candidate_files, desc=f"Stage zh [{dataset_name}]", total=len(candidate_files), unit="file"): 
            try:
                df = read_any_table(file_path)
            except Exception:
                continue
            for index, row in enumerate(df.to_dict(orient="records")):
                raw_text = text_candidates(row, ["input", "text", "query", "sentence", "utterance"])
                output_value = row.get("output") or row.get("response") or row.get("label") or row.get("target")
                if not raw_text and not output_value:
                    continue
                rows.append(
                    {
                        "zh_record_id": f"{dataset_name}:{file_path.stem}:{index}",
                        "dataset_name": dataset_name,
                        "raw_input_text": raw_text,
                        "raw_output_json": maybe_parse_json_string(output_value),
                        "source_file": str(file_path.relative_to(raw_dir)),
                    }
                )
    return {"stg_zh_command": dedupe_for_spec("stg_zh_command", pd.DataFrame(rows))}


def build_canonical_and_bridges(
    staging_tables: dict[str, pd.DataFrame],
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, Any]]:
    """Map staging tables into canonical dimensions, facts, bridges, and build context."""

    context: dict[str, Any] = {
        "task_source_ref": {},
        "task_state_map": {},
        "task_action_set_map": {},
        "task_split_key": {},
    }

    stage_log("Canonical: dim_home")
    dim_home = build_dim_home(staging_tables)
    stage_log(f"Canonical dim_home rows={len(dim_home)}")
    stage_log("Canonical: dim_area")
    dim_area = build_dim_area(staging_tables, dim_home)
    stage_log(f"Canonical dim_area rows={len(dim_area)}")
    stage_log("Canonical: dim_device")
    dim_device = build_dim_device(staging_tables, dim_home, dim_area)
    stage_log(f"Canonical dim_device rows={len(dim_device)}")
    stage_log("Canonical: dim_entity")
    dim_entity = build_dim_entity(staging_tables, dim_device)
    stage_log(f"Canonical dim_entity rows={len(dim_entity)}")
    stage_log("Canonical: dim_user")
    dim_user = build_dim_user(staging_tables)
    stage_log(f"Canonical dim_user rows={len(dim_user)}")

    lookup = build_lookup_context(dim_home, dim_area, dim_device, dim_entity, dim_user)

    stage_log("Canonical facts: state snapshots")
    fact_state_snapshot, state_sensor_bridge = build_state_facts(staging_tables, lookup, context)
    stage_log(f"fact_state_snapshot rows={len(fact_state_snapshot)}, bridge_state_sensor_event rows={len(state_sensor_bridge)}")
    stage_log("Canonical facts: tasks")
    fact_task = build_task_facts(staging_tables, lookup, context)
    stage_log(f"fact_task rows={len(fact_task)}")
    stage_log("Canonical facts: actions")
    fact_action_set, fact_action_item = build_action_facts(staging_tables, lookup, context, fact_task)
    stage_log(f"fact_action_set rows={len(fact_action_set)}, fact_action_item rows={len(fact_action_item)}")

    stage_log("Bridge: candidate devices")
    candidate_bridge = build_candidate_bridge(staging_tables, fact_task, fact_action_item, dim_device, lookup)
    stage_log(f"bridge_task_candidate_device rows={len(candidate_bridge)}")
    stage_log("Bridge: episode source")
    episode_source_bridge = build_episode_source_bridge(context)
    stage_log(f"bridge_episode_source rows={len(episode_source_bridge)}")
    stage_log("Bridge: synthetic discussion")
    synthetic_discussion = build_synthetic_discussion(fact_task, candidate_bridge, fact_action_item)
    stage_log(f"synthetic_discussion rows={len(synthetic_discussion)}")

    canonical_tables = {
        "dim_home": dim_home,
        "dim_area": dim_area,
        "dim_device": dim_device,
        "dim_entity": dim_entity,
        "dim_user": dim_user,
        "fact_state_snapshot": fact_state_snapshot,
        "fact_task": fact_task,
        "fact_action_set": fact_action_set,
        "fact_action_item": fact_action_item,
    }
    bridge_tables = {
        "bridge_state_sensor_event": state_sensor_bridge,
        "bridge_task_candidate_device": candidate_bridge,
        "bridge_episode_source": episode_source_bridge,
        "synthetic_discussion": synthetic_discussion,
    }
    return canonical_tables, bridge_tables, context


def build_dim_home(staging_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build home dimension rows from real and synthetic home sources."""

    rows: list[dict[str, Any]] = []
    ha_home = staging_tables["stg_ha_home"]
    for row in ha_home.to_dict(orient="records"):
        rows.append(
            {
                "home_sk": sha1_key("home_assistant_datasets", row["ha_home_id"]),
                "home_source": "home_assistant",
                "source_home_id": row["ha_home_id"],
                "home_name": row["home_name"],
                "country_code": row["country_code"],
                "location_desc": row["location_desc"],
                "home_type": row["home_type"],
                "is_synthetic": False,
                "source_dataset": "home_assistant_datasets",
            }
        )
    smartsense_regions = (
        sorted(staging_tables["stg_smartsense_log_action"]["region_or_country"].dropna().astype(str).unique())
        if not staging_tables["stg_smartsense_log_action"].empty
        else []
    )
    for region in smartsense_regions:
        rows.append(
            {
                "home_sk": sha1_key("smartsense", region),
                "home_source": "smartsense_region",
                "source_home_id": region,
                "home_name": f"SmartSense {region}",
                "country_code": None,
                "location_desc": region,
                "home_type": "synthetic_region",
                "is_synthetic": True,
                "source_dataset": "smartsense",
            }
        )
    casas_home_ids = (
        sorted(staging_tables["stg_casas_event"]["casas_home_id"].dropna().astype(str).unique())
        if not staging_tables["stg_casas_event"].empty
        else []
    )
    for home_id in casas_home_ids:
        rows.append(
            {
                "home_sk": sha1_key("casas_zenodo", home_id),
                "home_source": "casas_home",
                "source_home_id": home_id,
                "home_name": home_id,
                "country_code": None,
                "location_desc": "CASAS home",
                "home_type": "sensor_home",
                "is_synthetic": False,
                "source_dataset": "casas_zenodo",
            }
        )
    edge_persona_ids = (
        sorted(staging_tables["stg_edge_character"]["persona_id"].dropna().astype(str).unique())
        if not staging_tables["stg_edge_character"].empty
        else []
    )
    for persona_id in edge_persona_ids:
        rows.append(
            {
                "home_sk": sha1_key("edgewisepersona", f"home:{persona_id}"),
                "home_source": "persona_home",
                "source_home_id": f"home:{persona_id}",
                "home_name": f"Persona Home {persona_id}",
                "country_code": None,
                "location_desc": "Synthetic persona home",
                "home_type": "synthetic_persona_home",
                "is_synthetic": True,
                "source_dataset": "edgewisepersona",
            }
        )
    if not staging_tables["stg_zh_command"].empty:
        rows.append(
            {
                "home_sk": sha1_key("zh_commands", "shared_home"),
                "home_source": "zh_shared_home",
                "source_home_id": "shared_home",
                "home_name": "ZH Shared Home",
                "country_code": "CN",
                "location_desc": "Shared synthetic home for command parsing",
                "home_type": "synthetic_command_home",
                "is_synthetic": True,
                "source_dataset": "zh_commands",
            }
        )
    return dedupe_for_spec("dim_home", pd.DataFrame(rows))


def build_dim_area(staging_tables: dict[str, pd.DataFrame], dim_home: pd.DataFrame) -> pd.DataFrame:
    """Build area dimension rows across Home Assistant, CASAS, and synthetic homes."""

    home_lookup = {(row["source_dataset"], row["source_home_id"]): row["home_sk"] for row in dim_home.to_dict(orient="records")}
    rows: list[dict[str, Any]] = []
    for row in staging_tables["stg_ha_area"].to_dict(orient="records"):
        home_sk = home_lookup.get(("home_assistant_datasets", row["ha_home_id"]))
        if not home_sk:
            continue
        area_name_norm = normalize_area_name(row["area_name"])
        rows.append(
            {
                "area_sk": sha1_key(home_sk, area_name_norm),
                "home_sk": home_sk,
                "area_name_raw": row["area_name"],
                "area_name_norm": area_name_norm,
                "area_type": area_name_norm,
            }
        )
    casas_events = staging_tables["stg_casas_event"]
    if not casas_events.empty:
        for (home_id, room_hint), _group in casas_events.groupby(["casas_home_id", "sensor_room_hint"]):
            home_sk = home_lookup.get(("casas_zenodo", home_id))
            if not home_sk:
                continue
            area_name_norm = normalize_area_name(room_hint)
            rows.append(
                {
                    "area_sk": sha1_key(home_sk, area_name_norm),
                    "home_sk": home_sk,
                    "area_name_raw": room_hint,
                    "area_name_norm": area_name_norm,
                    "area_type": area_name_norm,
                }
            )
    edge_persona_ids = (
        staging_tables["stg_edge_character"]["persona_id"].dropna().astype(str).unique()
        if not staging_tables["stg_edge_character"].empty
        else []
    )
    for persona_id in edge_persona_ids:
        home_sk = home_lookup.get(("edgewisepersona", f"home:{persona_id}"))
        if not home_sk:
            continue
        rows.append(
            {
                "area_sk": sha1_key(home_sk, "other"),
                "home_sk": home_sk,
                "area_name_raw": "other",
                "area_name_norm": "other",
                "area_type": "other",
            }
        )
    if home_lookup.get(("zh_commands", "shared_home")):
        home_sk = home_lookup[("zh_commands", "shared_home")]
        rows.append(
            {
                "area_sk": sha1_key(home_sk, "other"),
                "home_sk": home_sk,
                "area_name_raw": "other",
                "area_name_norm": "other",
                "area_type": "other",
            }
        )
    return dedupe_for_spec("dim_area", pd.DataFrame(rows))


def build_dim_device(staging_tables: dict[str, pd.DataFrame], dim_home: pd.DataFrame, dim_area: pd.DataFrame) -> pd.DataFrame:
    """Build device dimension rows from explicit devices plus synthetic device projections."""

    home_lookup = {(row["source_dataset"], row["source_home_id"]): row["home_sk"] for row in dim_home.to_dict(orient="records")}
    area_lookup = {(row["home_sk"], row["area_name_norm"]): row["area_sk"] for row in dim_area.to_dict(orient="records")}
    rows: list[dict[str, Any]] = []

    for row in staging_tables["stg_ha_device"].to_dict(orient="records"):
        home_sk = home_lookup.get(("home_assistant_datasets", row["ha_home_id"]))
        if not home_sk:
            continue
        area_name_norm = normalize_area_name(row["area_name"])
        device_name_norm = normalize_text(row["device_name"])
        rows.append(
            {
                "device_sk": sha1_key(home_sk, area_name_norm or "NA", device_name_norm),
                "home_sk": home_sk,
                "area_sk": area_lookup.get((home_sk, area_name_norm)),
                "device_name_raw": row["device_name"],
                "device_name_norm": device_name_norm,
                "device_domain": normalize_device_domain(row["device_type_raw"] or row["device_name"]),
                "device_type_raw": row["device_type_raw"],
                "manufacturer_raw": row["manufacturer_raw"],
                "model_raw": row["model_raw"],
                "source_dataset": "home_assistant_datasets",
            }
        )
    for row in staging_tables["stg_smartsense_dict"].to_dict(orient="records"):
        if row["dict_type"] != "device_dict":
            continue
        home_sk = home_lookup.get(("smartsense", row["region_or_country"]))
        if not home_sk:
            continue
        device_name_norm = normalize_text(row["raw_name"])
        rows.append(
            {
                "device_sk": sha1_key(home_sk, "other", device_name_norm),
                "home_sk": home_sk,
                "area_sk": area_lookup.get((home_sk, "other")),
                "device_name_raw": row["raw_name"],
                "device_name_norm": device_name_norm,
                "device_domain": normalize_device_domain(row["raw_name"]),
                "device_type_raw": row["raw_name"],
                "manufacturer_raw": None,
                "model_raw": None,
                "source_dataset": "smartsense",
            }
        )
    for row in staging_tables["stg_edge_routine"].to_dict(orient="records"):
        home_sk = home_lookup.get(("edgewisepersona", f"home:{row['persona_id']}"))
        if not home_sk:
            continue
        action_json = row["action_json"] if isinstance(row["action_json"], dict) else maybe_parse_json_string(row["action_json"]) or {}
        for device_name in action_json.keys():
            device_name_norm = normalize_text(device_name)
            rows.append(
                {
                    "device_sk": sha1_key(home_sk, "other", device_name_norm),
                    "home_sk": home_sk,
                    "area_sk": area_lookup.get((home_sk, "other")),
                    "device_name_raw": device_name,
                    "device_name_norm": device_name_norm,
                    "device_domain": normalize_device_domain(device_name),
                    "device_type_raw": device_name,
                    "manufacturer_raw": None,
                    "model_raw": None,
                    "source_dataset": "edgewisepersona",
                }
            )
    zh_home_sk = home_lookup.get(("zh_commands", "shared_home"))
    if zh_home_sk:
        area_sk = area_lookup.get((zh_home_sk, "other"))
        for row in staging_tables["stg_zh_command"].to_dict(orient="records"):
            parsed = parse_zh_output(row["raw_output_json"])
            for device_name in [parsed.get("device"), parsed.get("entity_id")]:
                if not device_name:
                    continue
                device_name_norm = normalize_text(device_name)
                rows.append(
                    {
                        "device_sk": sha1_key(zh_home_sk, "other", device_name_norm),
                        "home_sk": zh_home_sk,
                        "area_sk": area_sk,
                        "device_name_raw": device_name,
                        "device_name_norm": device_name_norm,
                        "device_domain": normalize_device_domain(device_name),
                        "device_type_raw": device_name,
                        "manufacturer_raw": None,
                        "model_raw": None,
                        "source_dataset": "zh_commands",
                    }
                )
    return dedupe_for_spec("dim_device", pd.DataFrame(rows))


def build_dim_entity(staging_tables: dict[str, pd.DataFrame], dim_device: pd.DataFrame) -> pd.DataFrame:
    """Build entity dimension rows from Home Assistant and synthetic device entities."""

    rows: list[dict[str, Any]] = []
    for row in staging_tables["stg_ha_entity"].to_dict(orient="records"):
        device_name_norm = normalize_text(row["device_name"])
        candidate_devices = [item for item in dim_device.to_dict(orient="records") if item["device_name_norm"] == device_name_norm]
        if not candidate_devices:
            continue
        device_sk = candidate_devices[0]["device_sk"]
        rows.append(
            {
                "entity_sk": sha1_key(device_sk, row["entity_id"]),
                "device_sk": device_sk,
                "entity_id": row["entity_id"],
                "entity_domain": row["entity_domain"] or normalize_device_domain(row["entity_id"]),
                "entity_name_norm": normalize_text(row["entity_id"]),
            }
        )
    for row in dim_device.to_dict(orient="records"):
        entity_id = f"{row['device_domain']}.{row['device_name_norm']}"
        rows.append(
            {
                "entity_sk": sha1_key(row["device_sk"], entity_id),
                "device_sk": row["device_sk"],
                "entity_id": entity_id,
                "entity_domain": row["device_domain"],
                "entity_name_norm": row["device_name_norm"],
            }
        )
    return dedupe_for_spec("dim_entity", pd.DataFrame(rows))


def build_dim_user(staging_tables: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Build user dimension rows from personas and dataset-level fallback users."""

    rows: list[dict[str, Any]] = []
    for row in staging_tables["stg_edge_character"].to_dict(orient="records"):
        rows.append(
            {
                "user_sk": sha1_key("edgewisepersona", row["persona_id"]),
                "source_user_id": row["persona_id"],
                "user_type": "persona",
                "persona_profile_json": row["persona_json"],
                "source_dataset": "edgewisepersona",
            }
        )
    for dataset_name in ["home_assistant_datasets", "smartsense", "casas_zenodo", "zh_commands"]:
        rows.append(
            {
                "user_sk": sha1_key(dataset_name, "default_user"),
                "source_user_id": "default_user",
                "user_type": "default",
                "persona_profile_json": None,
                "source_dataset": dataset_name,
            }
        )
    return dedupe_for_spec("dim_user", pd.DataFrame(rows))


def build_state_facts(staging_tables: dict[str, pd.DataFrame], lookup: dict[str, Any], context: dict[str, Any]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build state snapshots and the CASAS state-to-event bridge."""

    rows: list[dict[str, Any]] = []
    bridge_rows: list[dict[str, Any]] = []

    for record in staging_tables["stg_ha_assist_record"].to_dict(orient="records"):
        home_sk = lookup["home_by_source"].get(("home_assistant_datasets", record["fixture_home_ref"]))
        user_sk = lookup["default_user_by_dataset"]["home_assistant_datasets"]
        snapshot_ts = synthetic_timestamp(record["ha_record_id"])
        state_id = make_state_id(home_sk, snapshot_ts, "task_aligned", "home_assistant_datasets")
        rows.append(
            {
                "state_id": state_id,
                "home_sk": home_sk,
                "user_sk": user_sk,
                "snapshot_ts": snapshot_ts,
                "snapshot_granularity": "task_aligned",
                "occupancy_status": None,
                "active_area_sk": None,
                "activity_hint": record["category"],
                "sensor_summary_json": {},
                "device_state_json": record["setup_json"],
                "environment_json": {"fixture_home_ref": record["fixture_home_ref"]},
                "history_action_summary_json": {},
                "source_dataset": "home_assistant_datasets",
                "label_quality": "strong",
            }
        )
        context["task_state_map"][record["ha_record_id"]] = state_id

    smartsense_dict = build_smartsense_reverse_dicts(staging_tables["stg_smartsense_dict"])
    smartsense_logs = staging_tables["stg_smartsense_log_action"]
    if not smartsense_logs.empty:
        log_instance_total = smartsense_logs["log_instance_id"].nunique(dropna=False)
        for log_instance_id, group in iter_progress(smartsense_logs.groupby("log_instance_id", sort=False), desc="Build SmartSense state facts", total=int(log_instance_total), unit="instance"):
            region = str(group["region_or_country"].iloc[0])
            home_sk = lookup["home_by_source"].get(("smartsense", region))
            user_sk = lookup["default_user_by_dataset"]["smartsense"]
            snapshot_ts = synthetic_timestamp(log_instance_id)
            history_actions = [
                decode_smartsense_step(row, smartsense_dict.get(region, {}))
                for row in group.sort_values("step_index").iloc[:-1].to_dict(orient="records")
            ]
            rows.append(
                {
                    "state_id": make_state_id(home_sk, snapshot_ts, "log_context", "smartsense"),
                    "home_sk": home_sk,
                    "user_sk": user_sk,
                    "snapshot_ts": snapshot_ts,
                    "snapshot_granularity": "log_context",
                    "occupancy_status": None,
                    "active_area_sk": None,
                    "activity_hint": "next_action_prediction",
                    "sensor_summary_json": {},
                    "device_state_json": {},
                    "environment_json": {"region_or_country": region},
                    "history_action_summary_json": history_actions,
                    "source_dataset": "smartsense",
                    "label_quality": "strong",
                }
            )
            context["task_state_map"][log_instance_id] = make_state_id(home_sk, snapshot_ts, "log_context", "smartsense")

    casas_events = staging_tables["stg_casas_event"]
    casas_labels = staging_tables["stg_casas_activity_label"]
    for granularity in ["1min", "5min", "15min"]:
        if casas_events.empty:
            break
        with activity_scope(f"building CASAS state facts [{granularity}]"):
            stage_log(
                f"Preparing CASAS windows for {granularity}: events={len(casas_events)}, labels={len(casas_labels)}"
            )
            windowed = load_or_build_casas_window_states(casas_events, casas_labels, granularity, lookup)
            stage_log(f"CASAS {granularity} state windows ready: {len(windowed)}")
            for row in windowed.to_dict(orient="records"):
                rows.append(row)
            stage_log(f"Building CASAS sensor bridge for {granularity}")
            bridge_rows.extend(build_casas_state_sensor_bridge(windowed, casas_events, lookup))

    for record in staging_tables["stg_edge_session"].to_dict(orient="records"):
        home_sk = lookup["home_by_source"].get(("edgewisepersona", f"home:{record['persona_id']}"))
        user_sk = lookup["user_by_source"].get(("edgewisepersona", record["persona_id"]))
        snapshot_ts = synthetic_timestamp(record["session_id"])
        state_id = make_state_id(home_sk, snapshot_ts, "session_inferred", "edgewisepersona")
        meta = infer_edge_session_meta(record["dialogue_json"])
        rows.append(
            {
                "state_id": state_id,
                "home_sk": home_sk,
                "user_sk": user_sk,
                "snapshot_ts": snapshot_ts,
                "snapshot_granularity": "session_inferred",
                "occupancy_status": None,
                "active_area_sk": None,
                "activity_hint": meta.get("activity_hint"),
                "sensor_summary_json": {},
                "device_state_json": {},
                "environment_json": meta,
                "history_action_summary_json": {},
                "source_dataset": "edgewisepersona",
                "label_quality": "weak",
            }
        )
        context["task_state_map"][record["session_id"]] = state_id

    zh_home_sk = lookup["home_by_source"].get(("zh_commands", "shared_home"))
    zh_user_sk = lookup["default_user_by_dataset"]["zh_commands"]
    for record in staging_tables["stg_zh_command"].to_dict(orient="records"):
        snapshot_ts = synthetic_timestamp(record["zh_record_id"])
        state_id = make_state_id(zh_home_sk, snapshot_ts, "minimal", "zh_commands")
        rows.append(
            {
                "state_id": state_id,
                "home_sk": zh_home_sk,
                "user_sk": zh_user_sk,
                "snapshot_ts": snapshot_ts,
                "snapshot_granularity": "minimal",
                "occupancy_status": None,
                "active_area_sk": None,
                "activity_hint": "command_only",
                "sensor_summary_json": {},
                "device_state_json": {},
                "environment_json": {},
                "history_action_summary_json": {},
                "source_dataset": "zh_commands",
                "label_quality": "weak",
            }
        )
        context["task_state_map"][record["zh_record_id"]] = state_id

    return dedupe_for_spec("fact_state_snapshot", pd.DataFrame(rows)), dedupe_for_spec("bridge_state_sensor_event", pd.DataFrame(bridge_rows))


def build_task_facts(staging_tables: dict[str, pd.DataFrame], lookup: dict[str, Any], context: dict[str, Any]) -> pd.DataFrame:
    """Build canonical tasks from staged assist, automation, logs, routines, sessions, and commands."""

    rows: list[dict[str, Any]] = []
    for record in staging_tables["stg_ha_assist_record"].to_dict(orient="records"):
        home_sk = lookup["home_by_source"].get(("home_assistant_datasets", record["fixture_home_ref"]))
        user_sk = lookup["default_user_by_dataset"]["home_assistant_datasets"]
        for index, sentence in enumerate(as_list(record["sentence_list_json"])):
            task_id = sha1_key("home_assistant_datasets", record["ha_record_id"], sentence, record["category"])
            rows.append(
                {
                    "task_id": task_id,
                    "home_sk": home_sk,
                    "user_sk": user_sk,
                    "task_ts": synthetic_timestamp(f"{record['ha_record_id']}:{index}"),
                    "task_source": "user_nl",
                    "raw_text": sentence,
                    "normalized_text": normalize_text(sentence),
                    "parsed_slots_json": {"category": record["category"]},
                    "trigger_json": {"type": "voice"},
                    "priority": 1,
                    "target_area_sk": None,
                    "source_dataset": "home_assistant_datasets",
                    "label_quality": "strong",
                }
            )
            context["task_source_ref"][task_id] = ("home_assistant_datasets", record["ha_record_id"], "assist")
            context["task_state_map"][task_id] = context["task_state_map"].get(record["ha_record_id"])
            context["task_split_key"][task_id] = record["fixture_home_ref"]
    for record in staging_tables["stg_ha_automation_record"].to_dict(orient="records"):
        home_sk = lookup["home_by_source"].get(("home_assistant_datasets", record["fixture_home_ref"])) or lookup["home_by_source"].get(("home_assistant_datasets", record["fixture_home_ref"].split("_")[0]))
        user_sk = lookup["default_user_by_dataset"]["home_assistant_datasets"]
        trigger_json = extract_automation_trigger(record["expected_result_json"])
        task_id = sha1_key("home_assistant_datasets", record["automation_id"], record["problem_readme"], json.dumps(trigger_json, sort_keys=True))
        rows.append(
            {
                "task_id": task_id,
                "home_sk": home_sk,
                "user_sk": user_sk,
                "task_ts": synthetic_timestamp(record["automation_id"]),
                "task_source": "automation",
                "raw_text": record["problem_readme"],
                "normalized_text": normalize_text(record["problem_readme"]),
                "parsed_slots_json": {"automation_id": record["automation_id"]},
                "trigger_json": trigger_json,
                "priority": 1,
                "target_area_sk": None,
                "source_dataset": "home_assistant_datasets",
                "label_quality": "medium",
            }
        )
        context["task_source_ref"][task_id] = ("home_assistant_datasets", record["automation_id"], "automation")
        context["task_split_key"][task_id] = record["fixture_home_ref"]
    logs = staging_tables["stg_smartsense_log_action"]
    if not logs.empty:
        log_instance_total = logs["log_instance_id"].nunique(dropna=False)
        for log_instance_id, group in iter_progress(logs.groupby("log_instance_id", sort=False), desc="Build SmartSense tasks", total=int(log_instance_total), unit="instance"):
            region = str(group["region_or_country"].iloc[0])
            home_sk = lookup["home_by_source"].get(("smartsense", region))
            user_sk = lookup["default_user_by_dataset"]["smartsense"]
            task_id = sha1_key("smartsense", log_instance_id, "predict_next_action_from_history")
            rows.append(
                {
                    "task_id": task_id,
                    "home_sk": home_sk,
                    "user_sk": user_sk,
                    "task_ts": synthetic_timestamp(log_instance_id),
                    "task_source": "inferred",
                    "raw_text": None,
                    "normalized_text": None,
                    "parsed_slots_json": {"log_instance_id": log_instance_id},
                    "trigger_json": {"type": "condition", "detail": "predict_next_action_from_history"},
                    "priority": 1,
                    "target_area_sk": None,
                    "source_dataset": "smartsense",
                    "label_quality": "strong",
                }
            )
            context["task_source_ref"][task_id] = ("smartsense", log_instance_id, "log_instance")
            context["task_state_map"][task_id] = context["task_state_map"].get(log_instance_id)
            context["task_split_key"][task_id] = log_instance_id
        routine_total = staging_tables["stg_smartsense_routine_device"]["routine_id"].nunique(dropna=False)
        for routine_id, group in iter_progress(staging_tables["stg_smartsense_routine_device"].groupby("routine_id", sort=False), desc="Build SmartSense routine tasks", total=int(routine_total), unit="routine"):
            region = str(group["region_or_country"].iloc[0])
            home_sk = lookup["home_by_source"].get(("smartsense", region))
            user_sk = lookup["default_user_by_dataset"]["smartsense"]
            task_id = sha1_key("smartsense", routine_id, "routine")
            rows.append(
                {
                    "task_id": task_id,
                    "home_sk": home_sk,
                    "user_sk": user_sk,
                    "task_ts": synthetic_timestamp(routine_id),
                    "task_source": "routine",
                    "raw_text": f"SmartSense routine {routine_id}",
                    "normalized_text": normalize_text(f"SmartSense routine {routine_id}"),
                    "parsed_slots_json": {"routine_id": routine_id},
                    "trigger_json": {"type": "habit", "detail": region},
                    "priority": 1,
                    "target_area_sk": None,
                    "source_dataset": "smartsense",
                    "label_quality": "weak",
                }
            )
            context["task_source_ref"][task_id] = ("smartsense", routine_id, "routine")
            context["task_split_key"][task_id] = routine_id
    for record in staging_tables["stg_edge_routine"].to_dict(orient="records"):
        home_sk = lookup["home_by_source"].get(("edgewisepersona", f"home:{record['persona_id']}"))
        user_sk = lookup["user_by_source"].get(("edgewisepersona", record["persona_id"]))
        task_id = sha1_key("edgewisepersona", record["routine_id"], record["routine_text"], json.dumps(record["trigger_json"], sort_keys=True))
        rows.append(
            {
                "task_id": task_id,
                "home_sk": home_sk,
                "user_sk": user_sk,
                "task_ts": synthetic_timestamp(record["routine_id"]),
                "task_source": "routine",
                "raw_text": record["routine_text"],
                "normalized_text": normalize_text(record["routine_text"]),
                "parsed_slots_json": {},
                "trigger_json": record["trigger_json"],
                "priority": 1,
                "target_area_sk": None,
                "source_dataset": "edgewisepersona",
                "label_quality": "weak",
            }
        )
        context["task_source_ref"][task_id] = ("edgewisepersona", record["routine_id"], "routine")
        context["task_split_key"][task_id] = record["persona_id"]
    for record in staging_tables["stg_edge_session"].to_dict(orient="records"):
        home_sk = lookup["home_by_source"].get(("edgewisepersona", f"home:{record['persona_id']}"))
        user_sk = lookup["user_by_source"].get(("edgewisepersona", record["persona_id"]))
        raw_text = extract_user_text_from_dialogue(record["dialogue_json"])
        task_id = sha1_key("edgewisepersona", record["session_id"], raw_text, json.dumps(record["ground_truth_routine_ids_json"], sort_keys=True))
        rows.append(
            {
                "task_id": task_id,
                "home_sk": home_sk,
                "user_sk": user_sk,
                "task_ts": synthetic_timestamp(record["session_id"]),
                "task_source": "user_nl",
                "raw_text": raw_text,
                "normalized_text": normalize_text(raw_text),
                "parsed_slots_json": {"routine_ids": record["ground_truth_routine_ids_json"]},
                "trigger_json": {"type": "habit", "detail": record["ground_truth_routine_ids_json"]},
                "priority": 1,
                "target_area_sk": None,
                "source_dataset": "edgewisepersona",
                "label_quality": "weak",
            }
        )
        context["task_source_ref"][task_id] = ("edgewisepersona", record["session_id"], "session")
        context["task_state_map"][task_id] = context["task_state_map"].get(record["session_id"])
        context["task_split_key"][task_id] = record["persona_id"]
    zh_home_sk = lookup["home_by_source"].get(("zh_commands", "shared_home"))
    zh_user_sk = lookup["default_user_by_dataset"]["zh_commands"]
    for record in staging_tables["stg_zh_command"].to_dict(orient="records"):
        parsed = parse_zh_output(record["raw_output_json"])
        task_id = sha1_key("zh_commands", record["zh_record_id"], record["raw_input_text"], json.dumps(parsed, sort_keys=True, ensure_ascii=False))
        rows.append(
            {
                "task_id": task_id,
                "home_sk": zh_home_sk,
                "user_sk": zh_user_sk,
                "task_ts": synthetic_timestamp(record["zh_record_id"]),
                "task_source": "user_nl",
                "raw_text": record["raw_input_text"],
                "normalized_text": normalize_text(record["raw_input_text"]),
                "parsed_slots_json": parsed,
                "trigger_json": {"type": "voice", "detail": parsed.get("datetime") or parsed.get("schedule")},
                "priority": 1,
                "target_area_sk": lookup["area_by_home_room"].get((zh_home_sk, normalize_area_name(parsed.get("room")))) if parsed.get("room") else None,
                "source_dataset": "zh_commands",
                "label_quality": "medium" if parsed.get("action") or parsed.get("intent") else "weak",
            }
        )
        context["task_source_ref"][task_id] = ("zh_commands", record["zh_record_id"], "command")
        context["task_state_map"][task_id] = context["task_state_map"].get(record["zh_record_id"])
        context["task_split_key"][task_id] = zh_home_sk
    return dedupe_for_spec("fact_task", pd.DataFrame(rows))


def build_action_facts(
    staging_tables: dict[str, pd.DataFrame],
    lookup: dict[str, Any],
    context: dict[str, Any],
    fact_task: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build action sets and items from strong and weak supervision sources."""

    action_set_rows: list[dict[str, Any]] = []
    action_item_rows: list[dict[str, Any]] = []

    task_lookup = {item["task_id"]: item for item in fact_task.to_dict(orient="records")}
    for record in staging_tables["stg_ha_assist_record"].to_dict(orient="records"):
        actions = parse_ha_expect_changes(record["expect_changes_json"])
        for sentence in as_list(record["sentence_list_json"]):
            task_id = sha1_key("home_assistant_datasets", record["ha_record_id"], sentence, record["category"])
            if task_id not in task_lookup:
                continue
            action_set_id = make_action_set_id(task_id, "home_assistant_datasets", "expected_change")
            action_set_rows.append(
                {
                    "action_set_id": action_set_id,
                    "task_id": task_id,
                    "home_sk": task_lookup[task_id]["home_sk"],
                    "action_ts": task_lookup[task_id]["task_ts"],
                    "action_reason_type": "expected_change",
                    "action_count": len(actions),
                    "source_dataset": "home_assistant_datasets",
                    "label_quality": "strong",
                }
            )
            for sequence_index, action in enumerate(actions):
                resolved = resolve_device_and_entity(action["device_id"], action["domain"], lookup, task_lookup[task_id]["home_sk"])
                action_item_rows.append(
                    {
                        "action_item_id": make_action_item_id(action_set_id, resolved["device_sk"], action["service"], sequence_index),
                        "action_set_id": action_set_id,
                        "device_sk": resolved["device_sk"],
                        "entity_sk": resolved["entity_sk"],
                        "device_domain": action["domain"],
                        "service_name_norm": normalize_service(action["service"]),
                        "arguments_json": action["arguments"],
                        "target_state_json": action.get("target_state_json") or {},
                        "sequence_index": sequence_index,
                        "source_dataset": "home_assistant_datasets",
                    }
                )
            context["task_action_set_map"][task_id] = action_set_id
    for record in staging_tables["stg_ha_automation_record"].to_dict(orient="records"):
        task_id = sha1_key("home_assistant_datasets", record["automation_id"], record["problem_readme"], json.dumps(extract_automation_trigger(record["expected_result_json"]), sort_keys=True))
        if task_id not in task_lookup:
            continue
        actions = parse_automation_actions(record["expected_result_json"])
        action_set_id = make_action_set_id(task_id, "home_assistant_datasets", "rule")
        action_set_rows.append(
            {
                "action_set_id": action_set_id,
                "task_id": task_id,
                "home_sk": task_lookup[task_id]["home_sk"],
                "action_ts": task_lookup[task_id]["task_ts"],
                "action_reason_type": "rule",
                "action_count": len(actions),
                "source_dataset": "home_assistant_datasets",
                "label_quality": "medium" if actions else "weak",
            }
        )
        for sequence_index, action in enumerate(actions):
            resolved = resolve_device_and_entity(action["device_id"], action["domain"], lookup, task_lookup[task_id]["home_sk"])
            action_item_rows.append(
                {
                    "action_item_id": make_action_item_id(action_set_id, resolved["device_sk"], action["service"], sequence_index),
                    "action_set_id": action_set_id,
                    "device_sk": resolved["device_sk"],
                    "entity_sk": resolved["entity_sk"],
                    "device_domain": action["domain"],
                    "service_name_norm": normalize_service(action["service"]),
                    "arguments_json": action["arguments"],
                    "target_state_json": {},
                    "sequence_index": sequence_index,
                    "source_dataset": "home_assistant_datasets",
                }
            )
        context["task_action_set_map"][task_id] = action_set_id

    smartsense_reverse = build_smartsense_reverse_dicts(staging_tables["stg_smartsense_dict"])
    logs = staging_tables["stg_smartsense_log_action"]
    if not logs.empty:
        log_instance_total = logs["log_instance_id"].nunique(dropna=False)
        for log_instance_id, group in iter_progress(logs.groupby("log_instance_id", sort=False), desc="Build SmartSense action facts", total=int(log_instance_total), unit="instance"):
            task_id = sha1_key("smartsense", log_instance_id, "predict_next_action_from_history")
            if task_id not in task_lookup:
                continue
            region = str(group["region_or_country"].iloc[0])
            ordered = group.sort_values("step_index")
            target_step = ordered.iloc[-1].to_dict()
            decoded = decode_smartsense_step(target_step, smartsense_reverse.get(region, {}))
            resolved = resolve_device_and_entity(decoded["device_name"], decoded["domain"], lookup, task_lookup[task_id]["home_sk"])
            action_set_id = make_action_set_id(task_id, "smartsense", "label")
            action_set_rows.append(
                {
                    "action_set_id": action_set_id,
                    "task_id": task_id,
                    "home_sk": task_lookup[task_id]["home_sk"],
                    "action_ts": task_lookup[task_id]["task_ts"],
                    "action_reason_type": "label",
                    "action_count": 1,
                    "source_dataset": "smartsense",
                    "label_quality": "strong",
                }
            )
            action_item_rows.append(
                {
                    "action_item_id": make_action_item_id(action_set_id, resolved["device_sk"], decoded["service"], 0),
                    "action_set_id": action_set_id,
                    "device_sk": resolved["device_sk"],
                    "entity_sk": resolved["entity_sk"],
                    "device_domain": decoded["domain"],
                    "service_name_norm": normalize_service(decoded["service"]),
                    "arguments_json": decoded["arguments"],
                    "target_state_json": {},
                    "sequence_index": 0,
                    "source_dataset": "smartsense",
                }
            )
            context["task_action_set_map"][task_id] = action_set_id
    for record in staging_tables["stg_edge_routine"].to_dict(orient="records"):
        task_id = sha1_key("edgewisepersona", record["routine_id"], record["routine_text"], json.dumps(record["trigger_json"], sort_keys=True))
        if task_id not in task_lookup:
            continue
        actions = parse_edge_actions(record["action_json"])
        action_set_id = make_action_set_id(task_id, "edgewisepersona", "routine")
        action_set_rows.append(
            {
                "action_set_id": action_set_id,
                "task_id": task_id,
                "home_sk": task_lookup[task_id]["home_sk"],
                "action_ts": task_lookup[task_id]["task_ts"],
                "action_reason_type": "routine",
                "action_count": len(actions),
                "source_dataset": "edgewisepersona",
                "label_quality": "weak" if actions else "weak",
            }
        )
        for sequence_index, action in enumerate(actions):
            resolved = resolve_device_and_entity(action["device_id"], action["domain"], lookup, task_lookup[task_id]["home_sk"])
            action_item_rows.append(
                {
                    "action_item_id": make_action_item_id(action_set_id, resolved["device_sk"], action["service"], sequence_index),
                    "action_set_id": action_set_id,
                    "device_sk": resolved["device_sk"],
                    "entity_sk": resolved["entity_sk"],
                    "device_domain": action["domain"],
                    "service_name_norm": normalize_service(action["service"]),
                    "arguments_json": action["arguments"],
                    "target_state_json": {},
                    "sequence_index": sequence_index,
                    "source_dataset": "edgewisepersona",
                }
            )
        context["task_action_set_map"][task_id] = action_set_id
    for record in staging_tables["stg_zh_command"].to_dict(orient="records"):
        parsed = parse_zh_output(record["raw_output_json"])
        task_id = sha1_key("zh_commands", record["zh_record_id"], record["raw_input_text"], json.dumps(parsed, sort_keys=True, ensure_ascii=False))
        if task_id not in task_lookup:
            continue
        actions = parse_zh_actions(parsed)
        if not actions:
            continue
        action_set_id = make_action_set_id(task_id, "zh_commands", "label")
        action_set_rows.append(
            {
                "action_set_id": action_set_id,
                "task_id": task_id,
                "home_sk": task_lookup[task_id]["home_sk"],
                "action_ts": task_lookup[task_id]["task_ts"],
                "action_reason_type": "label",
                "action_count": len(actions),
                "source_dataset": "zh_commands",
                "label_quality": "medium",
            }
        )
        for sequence_index, action in enumerate(actions):
            resolved = resolve_device_and_entity(action["device_id"], action["domain"], lookup, task_lookup[task_id]["home_sk"])
            action_item_rows.append(
                {
                    "action_item_id": make_action_item_id(action_set_id, resolved["device_sk"], action["service"], sequence_index),
                    "action_set_id": action_set_id,
                    "device_sk": resolved["device_sk"],
                    "entity_sk": resolved["entity_sk"],
                    "device_domain": action["domain"],
                    "service_name_norm": normalize_service(action["service"]),
                    "arguments_json": action["arguments"],
                    "target_state_json": {},
                    "sequence_index": sequence_index,
                    "source_dataset": "zh_commands",
                }
            )
        context["task_action_set_map"][task_id] = action_set_id

    return dedupe_for_spec("fact_action_set", pd.DataFrame(action_set_rows)), dedupe_for_spec("fact_action_item", pd.DataFrame(action_item_rows))


def build_candidate_bridge(
    staging_tables: dict[str, pd.DataFrame],
    fact_task: pd.DataFrame,
    fact_action_item: pd.DataFrame,
    dim_device: pd.DataFrame,
    lookup: dict[str, Any],
) -> pd.DataFrame:
    """Generate candidate devices from explicit mentions, room matches, and SmartSense co-occurrence."""

    rows: list[dict[str, Any]] = []
    device_rows = dim_device.to_dict(orient="records")
    devices_by_home: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for device in device_rows:
        devices_by_home[device["home_sk"]].append(device)
    cooccur_scores = build_smartsense_cooccur(staging_tables)
    fact_task_records = fact_task.to_dict(orient="records")
    stage_log(
        f"Candidate bridge inputs: tasks={len(fact_task_records)}, devices={len(device_rows)}, homes={len(devices_by_home)}"
    )
    for task in iter_progress(fact_task_records, desc="Build candidate bridge", total=len(fact_task_records), unit="task"):
        parsed_slots = maybe_parse_json_string(task["parsed_slots_json"]) if isinstance(task["parsed_slots_json"], str) else task["parsed_slots_json"]
        parsed_slots = parsed_slots or {}
        matched: dict[tuple[str, str], float] = {}
        explicit_text = " ".join([str(task.get("raw_text") or ""), json.dumps(parsed_slots, ensure_ascii=False)]).lower()
        for device in devices_by_home.get(task["home_sk"], []):
            if device["device_name_raw"] and str(device["device_name_raw"]).lower() in explicit_text:
                matched[(device["device_sk"], "explicit_mention")] = max(matched.get((device["device_sk"], "explicit_mention"), 0.0), 1.0)
            if parsed_slots.get("device") and normalize_text(parsed_slots.get("device")) == device["device_name_norm"]:
                matched[(device["device_sk"], "explicit_mention")] = max(matched.get((device["device_sk"], "explicit_mention"), 0.0), 1.0)
            if parsed_slots.get("room"):
                room_norm = normalize_area_name(parsed_slots.get("room"))
                if lookup["area_by_home_room"].get((task["home_sk"], room_norm)) == device["area_sk"]:
                    matched[(device["device_sk"], "room_match")] = max(matched.get((device["device_sk"], "room_match"), 0.0), 0.8)
        if task.get("target_area_sk"):
            for device in devices_by_home.get(task["home_sk"], []):
                if device["area_sk"] == task["target_area_sk"]:
                    matched[(device["device_sk"], "room_match")] = max(matched.get((device["device_sk"], "room_match"), 0.0), 0.75)
        cooccur_seed = [row["device_sk"] for row in device_rows if row["home_sk"] == task["home_sk"] and (row["device_name_raw"] or "").lower() in explicit_text]
        for seed_device_sk in cooccur_seed:
            for target_device_sk, score in cooccur_scores.get(seed_device_sk, {}).items():
                matched[(target_device_sk, "history_cooccur")] = max(matched.get((target_device_sk, "history_cooccur"), 0.0), float(score))
        home_inventory_devices = devices_by_home.get(task["home_sk"], [])
        for device in home_inventory_devices[:10]:
            matched.setdefault((device["device_sk"], "ha_inventory"), 0.2)
        ranked = sorted(matched.items(), key=lambda item: (-item[1], item[0][0]))
        for rank, ((device_sk, candidate_source), score) in enumerate(ranked, start=1):
            rows.append(
                {
                    "task_id": task["task_id"],
                    "device_sk": device_sk,
                    "candidate_rank": rank,
                    "candidate_source": candidate_source,
                    "candidate_score": round(score, 4),
                }
            )
    return dedupe_for_spec("bridge_task_candidate_device", pd.DataFrame(rows))


def build_episode_source_bridge(context: dict[str, Any]) -> pd.DataFrame:
    """Build source trace rows that connect episode samples back to raw source ids."""

    rows: list[dict[str, Any]] = []
    for task_id, ref in context.get("task_source_ref", {}).items():
        source_dataset, source_record_id, source_role = ref
        action_set_id = context.get("task_action_set_map", {}).get(task_id)
        state_id = context.get("task_state_map", {}).get(task_id)
        if not action_set_id or not state_id:
            continue
        sample_id = sha1_key(state_id, task_id, action_set_id)
        rows.append(
            {
                "sample_id": sample_id,
                "source_dataset": source_dataset,
                "source_record_id": source_record_id,
                "source_role": source_role,
            }
        )
    return dedupe_for_spec("bridge_episode_source", pd.DataFrame(rows))


def build_synthetic_discussion(
    fact_task: pd.DataFrame,
    candidate_bridge: pd.DataFrame,
    fact_action_item: pd.DataFrame,
) -> pd.DataFrame:
    """Generate synthetic device proposals from tasks and candidate devices."""

    target_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    action_set_to_task = {}
    for row in fact_action_item.to_dict(orient="records"):
        action_set_to_task.setdefault(row["action_set_id"], [])
        action_set_to_task[row["action_set_id"]].append(row)
    rows: list[dict[str, Any]] = []
    candidate_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not candidate_bridge.empty:
        for row in candidate_bridge.sort_values(["task_id", "candidate_rank"]).to_dict(orient="records"):
            if len(candidate_by_task[row["task_id"]]) < 3:
                candidate_by_task[row["task_id"]].append(row)
    fact_task_records = fact_task.to_dict(orient="records")
    stage_log(f"Synthetic discussion inputs: tasks={len(fact_task_records)}, candidate_rows={len(candidate_bridge)}")
    for task in iter_progress(fact_task_records, desc="Build synthetic discussion", total=len(fact_task_records), unit="task"):
        task_candidates = candidate_by_task.get(task["task_id"], [])
        for candidate in task_candidates:
            proposal_action = {
                "device_sk": candidate["device_sk"],
                "service_name_norm": "custom",
                "candidate_score": candidate["candidate_score"],
            }
            rows.append(
                {
                    "discussion_id": sha1_key(task["task_id"], candidate["device_sk"], candidate["candidate_source"]),
                    "task_id": task["task_id"],
                    "device_sk": candidate["device_sk"],
                    "proposal_text": f"Candidate device {candidate['device_sk']} may help fulfill task {task['task_id']}.",
                    "proposal_action_json": proposal_action,
                    "proposal_confidence": round(float(candidate["candidate_score"]), 4),
                    "proposal_type": candidate["candidate_source"],
                    "is_synthetic": True,
                }
            )
    return dedupe_for_spec("synthetic_discussion", pd.DataFrame(rows))


def build_episodes(
    canonical_tables: dict[str, pd.DataFrame],
    bridge_tables: dict[str, pd.DataFrame],
    context: dict[str, Any],
) -> pd.DataFrame:
    """Assemble final episode-level supervision rows."""

    fact_task = canonical_tables["fact_task"]
    fact_state = canonical_tables["fact_state_snapshot"]
    fact_action_set = canonical_tables["fact_action_set"]
    fact_action_item = canonical_tables["fact_action_item"]
    candidate_bridge = bridge_tables["bridge_task_candidate_device"]
    synthetic_discussion = bridge_tables["synthetic_discussion"]
    episode_source = bridge_tables["bridge_episode_source"]

    states_by_home = {
        home_sk: group.sort_values("snapshot_ts")
        for home_sk, group in fact_state.groupby("home_sk", sort=False)
    }
    task_by_id = {
        row["task_id"]: row for row in fact_task.to_dict(orient="records")
    }
    candidate_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not candidate_bridge.empty:
        for row in candidate_bridge.sort_values(["task_id", "candidate_rank"]).to_dict(orient="records"):
            candidate_by_task[row["task_id"]].append(row)
    action_items_by_set: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in fact_action_item.to_dict(orient="records"):
        action_items_by_set[row["action_set_id"]].append(row)
    discussion_by_task: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in synthetic_discussion.to_dict(orient="records"):
        discussion_by_task[row["task_id"]].append(row)
    source_by_sample: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in episode_source.to_dict(orient="records"):
        source_by_sample[row["sample_id"]].append(row)

    rows: list[dict[str, Any]] = []
    action_set_records = fact_action_set.to_dict(orient="records")
    stage_log(
        f"Episode assembly inputs: tasks={len(task_by_id)}, action_sets={len(action_set_records)}, candidates={len(candidate_bridge)}, discussions={len(synthetic_discussion)}"
    )
    for action_set in iter_progress(action_set_records, desc="Build episodes", total=len(action_set_records), unit="action_set"):
        task_row = task_by_id.get(action_set["task_id"])
        if task_row is None:
            continue
        state_id = context.get("task_state_map", {}).get(task_row["task_id"])
        if not state_id:
            state_id = find_nearest_state_id(states_by_home.get(task_row["home_sk"]), task_row["task_ts"])
        if not state_id:
            continue
        sample_id = sha1_key(state_id, task_row["task_id"], action_set["action_set_id"])
        candidate_devices = candidate_by_task.get(task_row["task_id"], [])
        target_actions = action_items_by_set.get(action_set["action_set_id"], [])
        source_rows = source_by_sample.get(sample_id, [])
        split_key = context.get("task_split_key", {}).get(task_row["task_id"]) or (
            task_row["user_sk"] if task_row["source_dataset"] == "edgewisepersona" else task_row["home_sk"]
        )
        rows.append(
            {
                "sample_id": sample_id,
                "home_sk": task_row["home_sk"],
                "user_sk": task_row["user_sk"],
                "state_id": state_id,
                "task_id": task_row["task_id"],
                "action_set_id": action_set["action_set_id"],
                "sample_ts": task_row["task_ts"] or action_set["action_ts"],
                "candidate_devices_json": candidate_devices,
                "target_actions_json": target_actions,
                "synthetic_discussion_json": discussion_by_task.get(task_row["task_id"], []),
                "source_mix_json": source_rows,
                "label_quality": merge_label_quality(task_row["label_quality"], action_set["label_quality"]),
                "split": split_for_id(str(split_key)),
            }
        )
    return dedupe_for_spec("episodes", pd.DataFrame(rows))


def build_lookup_context(
    dim_home: pd.DataFrame,
    dim_area: pd.DataFrame,
    dim_device: pd.DataFrame,
    dim_entity: pd.DataFrame,
    dim_user: pd.DataFrame,
) -> dict[str, Any]:
    """Build frequently-used lookup maps across the canonical dimensions."""

    return {
        "home_by_source": {(row["source_dataset"], row["source_home_id"]): row["home_sk"] for row in dim_home.to_dict(orient="records")},
        "area_by_home_room": {(row["home_sk"], row["area_name_norm"]): row["area_sk"] for row in dim_area.to_dict(orient="records")},
        "device_by_home_name": {(row["home_sk"], row["device_name_norm"]): row for row in dim_device.to_dict(orient="records")},
        "entity_by_device": {(row["device_sk"], row["entity_id"]): row["entity_sk"] for row in dim_entity.to_dict(orient="records")},
        "user_by_source": {(row["source_dataset"], row["source_user_id"]): row["user_sk"] for row in dim_user.to_dict(orient="records")},
        "default_user_by_dataset": {
            row["source_dataset"]: row["user_sk"] for row in dim_user.to_dict(orient="records") if row["source_user_id"] == "default_user"
        },
    }


def load_dataset_manifest() -> list[dict[str, Any]]:
    """Load the existing JSON dataset manifest when present."""

    return load_manifest(resolve_local_paths=True)


def read_any_table(path: Path) -> pd.DataFrame:
    """Read a small structured file into a dataframe."""

    suffix = path.suffix.lower()
    if suffix == ".csv":
        return pd.read_csv(path)
    if suffix == ".parquet":
        return pd.read_parquet(path)
    if suffix == ".jsonl":
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return pd.DataFrame(records)
    if suffix == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            return pd.DataFrame(payload)
        return pd.json_normalize(payload)
    raise ValueError(f"Unsupported input table: {path}")


def load_ha_yaml(path: Path) -> Any:
    """Load Home Assistant YAML while tolerating multi-doc and custom-tag documents."""

    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if "\n---" in text:
        docs = [doc for doc in yaml.load_all(text, Loader=HomeAssistantLoader) if doc is not None]
        if len(docs) == 1:
            return docs[0]
        return docs
    return yaml.load(text, Loader=HomeAssistantLoader)


def sha256_of_file(path: Path) -> str:
    """Return a stable SHA-256 digest for one file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha1_key(*parts: Any) -> str:
    """Generate a stable surrogate key using the requested SHA-1 strategy."""

    payload = ":".join(str(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def make_state_id(home_sk: str, snapshot_ts: str | None, granularity: str, source_dataset: str) -> str:
    """Build a stable state surrogate key."""

    return sha1_key(home_sk, snapshot_ts or "NA", granularity, source_dataset)


def make_action_set_id(task_id: str, source_dataset: str, action_reason_type: str) -> str:
    """Build a stable action-set surrogate key."""

    return sha1_key(task_id, source_dataset, action_reason_type)


def make_action_item_id(action_set_id: str, device_sk: str | None, service_name_norm: str, sequence_index: int) -> str:
    """Build a stable action-item surrogate key."""

    return sha1_key(action_set_id, device_sk or "NA", service_name_norm, sequence_index)


def synthetic_timestamp(seed: str) -> str:
    """Create a deterministic ISO timestamp for records without real timestamps."""

    base = datetime(2000, 1, 1, 0, 0, 0)
    offset = int(hashlib.sha1(seed.encode("utf-8")).hexdigest(), 16) % (365 * 24 * 3600)
    return (base + timedelta(seconds=offset)).isoformat()


def parse_datetime(date_text: Any, time_text: Any) -> datetime | None:
    """Parse a date/time pair into a ``datetime`` when possible."""

    for candidate in [
        f"{date_text} {time_text}",
        f"{date_text}T{time_text}",
    ]:
        try:
            return datetime.fromisoformat(str(candidate))
        except ValueError:
            continue
    return None


def normalize_text(value: Any) -> str:
    """Normalize free text into a compact snake_case token."""

    text = str(value or "").strip().lower()
    text = "".join(character if character.isalnum() else "_" for character in text)
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def normalize_area_name(value: Any) -> str:
    """Normalize room/area labels into the requested room enum."""

    room = normalize_room(value)
    if room in {
        "living_room",
        "bedroom",
        "kitchen",
        "bathroom",
        "office",
        "entry",
        "garage",
        "outdoor",
    }:
        return room
    if room in {"hallway", "hall"}:
        return "entry"
    return "other"


def normalize_device_domain(value: Any) -> str:
    """Normalize device domains into the canonical device-domain enum."""

    domain = normalize_domain(value)
    if domain in {"light", "climate", "fan", "switch", "cover", "media_player", "vacuum", "lock", "sensor"}:
        return domain
    if str(value or "").lower() in {"washer", "dishwasher", "oven", "dryer", "fridge", "refrigerator"}:
        return "appliance"
    return "other"


def _prepare_table(table_name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Align dataframe columns with the declarative schema."""

    spec = TABLE_SPECS[table_name]
    prepared = df.copy() if df is not None else pd.DataFrame()
    for column in spec.columns:
        if column not in prepared.columns:
            prepared[column] = None
    prepared = prepared[spec.columns]
    return prepared


def dedupe_for_spec(table_name: str, df: pd.DataFrame) -> pd.DataFrame:
    """Align columns and drop duplicate rows using the table's primary key when available."""

    prepared = _prepare_table(table_name, df)
    spec = TABLE_SPECS[table_name]
    if prepared.empty:
        return prepared
    if table_name in DEDUP_SKIP_TABLES:
        stage_log(
            f"Skip dedupe for {table_name}: rows={len(prepared)} reason=large_staging_table"
        )
        return prepared.reset_index(drop=True)
    stage_log(f"Dedupe start for {table_name}: rows={len(prepared)}")
    if spec.primary_key:
        deduped = prepared.drop_duplicates(subset=spec.primary_key).reset_index(drop=True)
    else:
        deduped = prepared.drop_duplicates().reset_index(drop=True)
    if len(deduped) != len(prepared):
        stage_log(f"Dedupe removed {len(prepared) - len(deduped)} rows for {table_name}")
    else:
        stage_log(f"Dedupe kept all rows for {table_name}")
    return deduped


def as_list(value: Any) -> list[Any]:
    """Convert null/scalar/list inputs into a list."""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def parse_ha_expect_changes(payload: Any) -> list[dict[str, Any]]:
    """Map Home Assistant expected state changes to canonical action items."""

    payload = maybe_parse_json_string(payload) or {}
    actions: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return actions
    for entity_id, change in payload.items():
        if not isinstance(change, dict):
            continue
        domain = normalize_device_domain(str(entity_id).split(".", 1)[0])
        attributes = change.get("attributes") or {}
        service = "custom"
        if "brightness" in attributes:
            service = "set_brightness"
        elif "temperature" in attributes:
            service = "set_temperature"
        else:
            state = str(change.get("state") or "").lower()
            service = {
                "on": "turn_on",
                "off": "turn_off",
                "open": "open",
                "closed": "close",
                "locked": "lock",
                "unlocked": "unlock",
                "playing": "play",
                "idle": "pause",
            }.get(state, "custom")
        actions.append(
            {
                "device_id": entity_id,
                "domain": domain,
                "service": service,
                "arguments": attributes or {"state": change.get("state")},
            }
        )
    return actions


def extract_automation_trigger(payload: Any) -> dict[str, Any]:
    """Extract a lightweight trigger summary from an automation YAML payload."""

    payload = maybe_parse_json_string(payload) or {}
    if isinstance(payload, list):
        payload = next((item for item in payload if isinstance(item, dict)), {})
    if isinstance(payload, dict):
        return {"type": "condition", "detail": payload.get("triggers") or payload.get("trigger")}
    return {"type": "condition", "detail": None}


def parse_automation_actions(payload: Any) -> list[dict[str, Any]]:
    """Extract action rows from Home Assistant automation solutions."""

    payload = maybe_parse_json_string(payload) or {}
    if isinstance(payload, list):
        payload = next((item for item in payload if isinstance(item, dict)), {})
    actions: list[dict[str, Any]] = []
    if not isinstance(payload, dict):
        return actions
    for item in payload.get("actions", []) or []:
        if not isinstance(item, dict):
            continue
        for then_item in item.get("then", []) or []:
            if not isinstance(then_item, dict):
                continue
            service_name = str(then_item.get("service") or "")
            entity_id = str((then_item.get("target") or {}).get("entity_id") or "")
            actions.append(
                {
                    "device_id": entity_id or service_name.split(".", 1)[0],
                    "domain": normalize_device_domain(entity_id.split(".", 1)[0] if "." in entity_id else service_name.split(".", 1)[0]),
                    "service": service_name.split(".", 1)[-1] if "." in service_name else service_name,
                    "arguments": then_item.get("data") or {},
                }
            )
    return actions


def build_smartsense_reverse_dicts(stg_dict: pd.DataFrame) -> dict[str, dict[str, dict[int, str]]]:
    """Build region-scoped reverse dictionaries for SmartSense ids."""

    result: dict[str, dict[str, dict[int, str]]] = defaultdict(lambda: defaultdict(dict))
    for row in stg_dict.to_dict(orient="records"):
        result[str(row["region_or_country"])][str(row["dict_type"])][int(row["raw_id"])] = str(row["raw_name"])
    return result


def decode_smartsense_step(row: dict[str, Any], reverse_dicts: dict[str, dict[int, str]]) -> dict[str, Any]:
    """Decode one SmartSense step into a human-readable action stub."""

    device_name = reverse_dicts.get("device_dict", {}).get(int(row["device_id_raw"]), str(row["device_id_raw"]))
    device_control = reverse_dicts.get("device_control_dict", {}).get(int(row["device_control_id_raw"]), "")
    service_name = device_control.split(":", 1)[-1] if ":" in device_control else str(row["control_id_raw"])
    return {
        "device_name": device_name,
        "domain": normalize_device_domain(device_name),
        "service": normalize_service(service_name),
        "arguments": {
            "day_of_week_id": row["day_of_week_id"],
            "hour_id": row["hour_id"],
            "control_id_raw": row["control_id_raw"],
            "device_control_id_raw": row["device_control_id_raw"],
        },
    }


def load_or_build_casas_window_states(
    casas_events: pd.DataFrame,
    casas_labels: pd.DataFrame,
    granularity: str,
    lookup: dict[str, Any],
) -> pd.DataFrame:
    """Use precomputed CASAS windows when available, otherwise fall back to raw aggregation."""

    precomputed_path = DATA_PROCESSED_DIR / "casas" / f"window_features_{granularity}.parquet"
    if precomputed_path.exists():
        stage_log(f"Loading precomputed CASAS windows from {precomputed_path}")
        try:
            precomputed = pd.read_parquet(precomputed_path)
            stage_log(f"Loaded precomputed CASAS windows for {granularity}: {len(precomputed)} rows")
            state_df = casas_precomputed_to_state_facts(precomputed, granularity, lookup)
            if not state_df.empty:
                return state_df
            stage_log(f"Precomputed CASAS windows were empty for {granularity}, falling back to raw events")
        except Exception as exc:
            stage_log(f"Failed to read precomputed CASAS windows for {granularity}: {exc}; falling back to raw events")
    return build_casas_window_states(casas_events, casas_labels, granularity, lookup)


def casas_precomputed_to_state_facts(precomputed: pd.DataFrame, granularity: str, lookup: dict[str, Any]) -> pd.DataFrame:
    """Map precomputed CASAS window features into canonical state snapshots."""

    if precomputed.empty:
        return pd.DataFrame(columns=TABLE_SPECS["fact_state_snapshot"].columns)

    stage_log(f"Mapping precomputed CASAS windows for {granularity}: input_rows={len(precomputed)}")
    df = precomputed.copy()
    home_column = "home_id" if "home_id" in df.columns else "casas_home_id"
    ts_column = "window_start" if "window_start" in df.columns else "timestamp"
    df[ts_column] = pd.to_datetime(df[ts_column], errors="coerce")
    df = df.dropna(subset=[ts_column]).reset_index(drop=True)
    stage_log(f"Precomputed CASAS rows remaining after timestamp cleanup for {granularity}: {len(df)}")
    if df.empty:
        return pd.DataFrame(columns=TABLE_SPECS["fact_state_snapshot"].columns)

    room_counts_list = []
    active_rooms_list = []
    active_room_norm_list = []
    activity_hints = []
    home_sks = []
    area_sks = []
    state_ids = []
    snapshot_ts_list = []
    occupancies = []
    sensor_summary_list = []

    for row in iter_progress(df.itertuples(index=False), desc=f"Map precomputed CASAS [{granularity}]", total=len(df), unit="window"):
        row_dict = row._asdict()
        home_id = row_dict.get(home_column)
        snapshot_ts = row_dict.get(ts_column)
        home_sk = lookup["home_by_source"].get(("casas_zenodo", home_id))
        room_counts = maybe_parse_json_string(row_dict.get("room_motion_counts_json")) or {}
        if not isinstance(room_counts, dict):
            room_counts = {}
        active_rooms = sorted(str(key) for key in room_counts.keys() if str(key).strip())
        active_room_raw = max(room_counts.items(), key=lambda item: item[1])[0] if room_counts else None
        active_room_norm = normalize_area_name(active_room_raw)
        state_id = make_state_id(home_sk, snapshot_ts.isoformat(), granularity, "casas_zenodo")
        occupancy_value = row_dict.get("occupancy")
        if isinstance(occupancy_value, str):
            occupancy_value = occupancy_value.lower() in {"true", "occupied", "1", "yes"}
        occupancy_value = bool(occupancy_value)
        sensor_summary = {
            "room_motion_counts": room_counts,
            "door_open_counts": maybe_parse_json_string(row_dict.get("door_open_counts_json")) or row_dict.get("door_open_counts_json"),
            "last_sensor_event_ts": str(row_dict.get("last_sensor_event_ts")) if row_dict.get("last_sensor_event_ts") else None,
            "distinct_active_rooms": active_rooms,
            "distinct_active_room_count": row_dict.get("distinct_active_rooms"),
            "event_count": row_dict.get("event_count"),
            "distinct_sensor_count": row_dict.get("distinct_sensor_count"),
        }

        room_counts_list.append(room_counts)
        active_rooms_list.append(active_rooms)
        active_room_norm_list.append(active_room_norm)
        activity_hints.append(row_dict.get("activity_hint"))
        home_sks.append(home_sk)
        area_sks.append(lookup["area_by_home_room"].get((home_sk, active_room_norm)))
        state_ids.append(state_id)
        snapshot_ts_list.append(snapshot_ts.isoformat())
        occupancies.append(occupancy_value)
        sensor_summary_list.append(sensor_summary)

    result = pd.DataFrame(
        {
            "state_id": state_ids,
            "home_sk": home_sks,
            "user_sk": lookup["default_user_by_dataset"]["casas_zenodo"],
            "snapshot_ts": snapshot_ts_list,
            "snapshot_granularity": granularity,
            "occupancy_status": occupancies,
            "active_area_sk": area_sks,
            "activity_hint": activity_hints,
            "sensor_summary_json": sensor_summary_list,
            "device_state_json": [{} for _ in state_ids],
            "environment_json": [{} for _ in state_ids],
            "history_action_summary_json": [{} for _ in state_ids],
            "source_dataset": "casas_zenodo",
            "label_quality": "weak",
        }
    )
    return dedupe_for_spec("fact_state_snapshot", result)


def iter_casas_rows(file_path: Path):
    """Yield normalized CASAS rows while merging overflow columns into the activity field."""

    with file_path.open("r", encoding="utf-8", errors="ignore", newline="") as handle:
        reader = csv.reader(handle)
        for row in reader:
            if not row or len(row) < 4:
                continue
            if len(row) == 4:
                row.append(None)
            elif len(row) > 5:
                row = row[:4] + [",".join(row[4:])]
            yield row[:5]


def read_casas_rows(file_path: Path) -> list[list[Any]]:
    """Read one CASAS CSV file while merging overflow columns into the activity field."""

    return list(iter_casas_rows(file_path))


def infer_casas_sensor_type(sensor_id: str, message: str) -> str:
    """Infer a coarse sensor type hint from CASAS sensor ids and messages."""

    sensor_id_lower = str(sensor_id).lower()
    if sensor_id_lower.startswith("d") or "door" in sensor_id_lower:
        return "door"
    if sensor_id_lower.startswith("m") or "motion" in sensor_id_lower:
        return "motion"
    if sensor_id_lower.startswith("t") or "temp" in sensor_id_lower:
        return "temperature"
    if sensor_id_lower.startswith("i"):
        return "item"
    return str(message).lower()


def parse_casas_activity(text: Any) -> tuple[str | None, str | None]:
    """Parse interval-style CASAS activity labels such as ``Sleep="begin"``."""

    if text is None:
        return None, None
    raw = str(text).strip()
    if not raw:
        return None, None
    if "=" not in raw:
        return raw, None
    label, phase = raw.split("=", 1)
    return label.strip(), phase.strip().strip('"')


def build_casas_window_states(
    casas_events: pd.DataFrame,
    casas_labels: pd.DataFrame,
    granularity: str,
    lookup: dict[str, Any],
) -> pd.DataFrame:
    """Aggregate CASAS events into canonical state windows."""

    if casas_events.empty:
        return pd.DataFrame(columns=TABLE_SPECS["fact_state_snapshot"].columns)
    window_floor = {"1min": "1min", "5min": "5min", "15min": "15min"}[granularity]
    stage_log(f"Starting raw CASAS window aggregation for {granularity}: events={len(casas_events)}, labels={len(casas_labels)}")
    events = casas_events.copy()
    events["event_ts"] = pd.to_datetime(events["event_ts"], errors="coerce")
    events = events.dropna(subset=["event_ts"])
    events["window_start"] = events["event_ts"].dt.floor(window_floor)
    stage_log(f"CASAS events retained for {granularity} after timestamp cleanup: {len(events)}")
    labels_by_home: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if not casas_labels.empty:
        labels = casas_labels.copy()
        labels["start_ts"] = pd.to_datetime(labels["start_ts"], errors="coerce")
        labels["end_ts"] = pd.to_datetime(labels["end_ts"], errors="coerce")
        labels = labels.dropna(subset=["start_ts", "end_ts"])
        for home_id, group in labels.groupby("casas_home_id", sort=False):
            labels_by_home[str(home_id)] = group[["start_ts", "end_ts", "activity_label_raw"]].to_dict(orient="records")
        stage_log(f"CASAS label homes indexed for {granularity}: {len(labels_by_home)}")
    rows: list[dict[str, Any]] = []
    window_total = events[["casas_home_id", "window_start"]].drop_duplicates().shape[0]
    stage_log(f"CASAS distinct windows for {granularity}: {window_total}")
    for (home_id, window_start), group in iter_progress(events.groupby(["casas_home_id", "window_start"], sort=False), desc=f"Build CASAS window states [{granularity}]", total=int(window_total), unit="window"):
        home_sk = lookup["home_by_source"].get(("casas_zenodo", home_id))
        if not home_sk:
            continue
        room_counts = Counter(item for item in group["sensor_room_hint"] if item)
        door_count = int((group["sensor_type_hint"] == "door").sum())
        motion_count = int((group["sensor_type_hint"] == "motion").sum())
        active_room = normalize_area_name(room_counts.most_common(1)[0][0]) if room_counts else "other"
        active_area_sk = lookup["area_by_home_room"].get((home_sk, active_room))
        overlapping_labels = []
        if labels_by_home:
            labels_for_home = labels_by_home.get(str(home_id), [])
            window_end = window_start + pd.Timedelta(window_floor)
            for label_row in labels_for_home:
                start_ts = label_row["start_ts"]
                end_ts = label_row["end_ts"]
                if start_ts <= window_end and end_ts >= window_start:
                    overlapping_labels.append(label_row["activity_label_raw"])
        snapshot_ts = window_start.isoformat()
        rows.append(
            {
                "state_id": make_state_id(home_sk, snapshot_ts, granularity, "casas_zenodo"),
                "home_sk": home_sk,
                "user_sk": lookup["default_user_by_dataset"]["casas_zenodo"],
                "snapshot_ts": snapshot_ts,
                "snapshot_granularity": granularity,
                "occupancy_status": bool(len(group)),
                "active_area_sk": active_area_sk,
                "activity_hint": overlapping_labels[0] if overlapping_labels else None,
                "sensor_summary_json": {
                    "room_motion_counts": dict(room_counts),
                    "door_open_counts": door_count,
                    "last_sensor_event_ts": group["event_ts"].max().isoformat() if not group.empty else None,
                    "distinct_active_rooms": sorted(set(item for item in group["sensor_room_hint"] if item)),
                },
                "device_state_json": {},
                "environment_json": {},
                "history_action_summary_json": {},
                "source_dataset": "casas_zenodo",
                "label_quality": "weak",
            }
        )
    return dedupe_for_spec("fact_state_snapshot", pd.DataFrame(rows))


def build_casas_state_sensor_bridge(
    windowed_states: pd.DataFrame,
    casas_events: pd.DataFrame,
    lookup: dict[str, Any],
) -> list[dict[str, Any]]:
    """Connect CASAS windows back to raw events with one merge per granularity."""

    if windowed_states.empty or casas_events.empty:
        return []

    home_reverse = {
        home_sk: source_home_id
        for (source_dataset, source_home_id), home_sk in lookup["home_by_source"].items()
        if source_dataset == "casas_zenodo"
    }
    events = casas_events.copy()
    events["event_ts"] = pd.to_datetime(events["event_ts"], errors="coerce")
    events = events.dropna(subset=["event_ts"]).copy()
    if events.empty:
        return []

    bridge_frames = []
    for granularity in ["1min", "5min", "15min"]:
        state_subset = windowed_states[windowed_states["snapshot_granularity"] == granularity].copy()
        if state_subset.empty:
            continue
        freq = {"1min": "1min", "5min": "5min", "15min": "15min"}[granularity]
        state_subset["window_start"] = pd.to_datetime(state_subset["snapshot_ts"], errors="coerce")
        state_subset["casas_home_id"] = state_subset["home_sk"].map(home_reverse)
        state_subset = state_subset.dropna(subset=["window_start", "casas_home_id"])
        if state_subset.empty:
            continue
        event_subset = events.copy()
        event_subset["window_start"] = event_subset["event_ts"].dt.floor(freq)
        merged = event_subset.merge(
            state_subset[["state_id", "casas_home_id", "window_start"]],
            on=["casas_home_id", "window_start"],
            how="inner",
        )
        if merged.empty:
            continue
        bridge_frames.append(
            merged[["state_id", "casas_home_id", "event_ts", "sensor_id_raw", "message_raw"]].assign(
                event_ts=lambda frame: frame["event_ts"].dt.strftime("%Y-%m-%dT%H:%M:%S")
            )
        )

    if not bridge_frames:
        return []
    return pd.concat(bridge_frames, ignore_index=True).to_dict(orient="records")


def infer_edge_session_meta(dialogue_json: Any) -> dict[str, Any]:
    """Infer weak session-level metadata from EdgeWisePersona dialogue."""

    messages = as_list(maybe_parse_json_string(dialogue_json))
    user_text = " ".join(item.get("text", "") for item in messages if isinstance(item, dict) and item.get("role") == "user").strip()
    return {
        "activity_hint": "dialogue_session" if user_text else None,
        "last_user_text": user_text or None,
    }


def routine_to_text(routine: dict[str, Any]) -> str:
    """Create a readable summary sentence for one persona routine."""

    triggers = routine.get("triggers") or {}
    actions = routine.get("actions") or {}
    return f"Routine with triggers {json.dumps(triggers, ensure_ascii=False)} and actions {json.dumps(actions, ensure_ascii=False)}"


def parse_edge_actions(payload: Any) -> list[dict[str, Any]]:
    """Map EdgeWisePersona structured routine actions into canonical action items."""

    payload = maybe_parse_json_string(payload) or {}
    if not isinstance(payload, dict):
        return []
    actions: list[dict[str, Any]] = []
    for device_name, arguments in payload.items():
        if arguments is None:
            continue
        arguments = arguments if isinstance(arguments, dict) else {"value": arguments}
        if "temperature" in arguments:
            service = "set_temperature"
        elif "brightness" in arguments:
            service = "set_brightness"
        elif "armed" in arguments:
            service = "lock" if arguments.get("armed") else "unlock"
        else:
            service = "custom"
        actions.append(
            {
                "device_id": device_name,
                "domain": normalize_device_domain(device_name),
                "service": service,
                "arguments": arguments,
            }
        )
    return actions


def extract_user_text_from_dialogue(dialogue_json: Any) -> str:
    """Concatenate user messages from a dialogue list."""

    messages = as_list(maybe_parse_json_string(dialogue_json))
    return " ".join(item.get("text", "") for item in messages if isinstance(item, dict) and item.get("role") == "user").strip()


def parse_zh_output(payload: Any) -> dict[str, Any]:
    """Parse Chinese command labels into a normalized slot dictionary."""

    payload = maybe_parse_json_string(payload)
    if isinstance(payload, dict) and "slots" in payload:
        slot_map = {item.get("name"): item.get("normValue") or item.get("value") for item in payload.get("slots", []) if isinstance(item, dict)}
        slot_map["intent"] = payload.get("intent")
        return slot_map
    if isinstance(payload, dict):
        return payload
    return {}


def parse_zh_actions(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """Map parsed Chinese command slots to canonical action rows."""

    if not isinstance(parsed, dict):
        return []
    action_value = parsed.get("action") or parsed.get("insType") or parsed.get("intent")
    device_value = parsed.get("device") or parsed.get("entity_id") or ""
    if not action_value and not device_value:
        return []
    return [
        {
            "device_id": device_value,
            "domain": normalize_device_domain(device_value),
            "service": normalize_service(action_value),
            "arguments": {
                "room": parsed.get("room"),
                "attribute": parsed.get("attribute") or parsed.get("attr"),
                "value": parsed.get("value") or parsed.get("attrValue"),
                "datetime": parsed.get("datetime") or parsed.get("delay"),
            },
        }
    ]


def resolve_device_and_entity(device_id: Any, domain: Any, lookup: dict[str, Any], home_sk: str | None) -> dict[str, Any]:
    """Resolve a device/entity reference against canonical dimensions with synthetic fallback."""

    device_name_norm = normalize_text(str(device_id).split(".", 1)[-1] if "." in str(device_id) else device_id)
    device_row = lookup["device_by_home_name"].get((home_sk, device_name_norm))
    if not device_row:
        device_sk = sha1_key(home_sk or "NA", "other", device_name_norm)
        entity_id = str(device_id) if "." in str(device_id) else f"{normalize_device_domain(domain)}.{device_name_norm}"
        return {
            "device_sk": device_sk,
            "entity_sk": sha1_key(device_sk, entity_id),
        }
    entity_id = str(device_id) if "." in str(device_id) else f"{device_row['device_domain']}.{device_row['device_name_norm']}"
    return {
        "device_sk": device_row["device_sk"],
        "entity_sk": lookup["entity_by_device"].get((device_row["device_sk"], entity_id), sha1_key(device_row["device_sk"], entity_id)),
    }


def build_smartsense_cooccur(staging_tables: dict[str, pd.DataFrame]) -> dict[str, dict[str, float]]:
    """Build a simple device co-occurrence matrix from SmartSense routines."""

    routine_df = staging_tables["stg_smartsense_routine_device"]
    dict_df = staging_tables["stg_smartsense_dict"]
    reverse = build_smartsense_reverse_dicts(dict_df)
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    for (_routine_id, region), group in routine_df.groupby(["routine_id", "region_or_country"], sort=False):
        names = []
        device_map = reverse.get(str(region), {}).get("device_dict", {})
        for row in group.to_dict(orient="records"):
            names.append(device_map.get(int(row["device_id_raw"]), str(row["device_id_raw"])))
        unique_names = sorted(set(names))
        for source_name in unique_names:
            source_sk = sha1_key(sha1_key("smartsense", region), "other", normalize_text(source_name))
            for target_name in unique_names:
                if source_name == target_name:
                    continue
                target_sk = sha1_key(sha1_key("smartsense", region), "other", normalize_text(target_name))
                counts[source_sk][target_sk] += 1
    normalized: dict[str, dict[str, float]] = {}
    for source_sk, counter in counts.items():
        total = sum(counter.values()) or 1
        normalized[source_sk] = {target_sk: round(value / total, 4) for target_sk, value in counter.items()}
    return normalized


def merge_label_quality(task_quality: Any, action_quality: Any) -> str:
    """Merge task/action label quality into one episode-level quality tag."""

    task_quality = str(task_quality or "weak")
    action_quality = str(action_quality or "weak")
    if task_quality == action_quality:
        return task_quality
    ordered = {name: index for index, name in enumerate(LABEL_QUALITY_ENUM)}
    if task_quality not in ordered or action_quality not in ordered:
        return "mixed"
    if abs(ordered[task_quality] - ordered[action_quality]) <= 1:
        return action_quality if ordered[action_quality] >= ordered[task_quality] else task_quality
    return "mixed"


def find_nearest_state_id(states: pd.DataFrame | None, task_ts: Any) -> str | None:
    """Find the nearest state at or before a task timestamp within one home."""

    if states is None or states.empty:
        return None
    if not task_ts:
        return states.iloc[-1]["state_id"]
    task_dt = pd.to_datetime(task_ts, errors="coerce")
    if pd.isna(task_dt):
        return states.iloc[-1]["state_id"]
    subset = states[pd.to_datetime(states["snapshot_ts"], errors="coerce") <= task_dt]
    if subset.empty:
        return states.iloc[0]["state_id"]
    return subset.iloc[-1]["state_id"]


def estimate_timestamp_parse_rate(staging_tables: dict[str, pd.DataFrame], canonical_tables: dict[str, pd.DataFrame]) -> dict[str, float]:
    """Estimate timestamp parse rates across timestamp-bearing tables."""

    result: dict[str, float] = {}
    for table_name, df in {**staging_tables, **canonical_tables}.items():
        timestamp_columns = [column for column in df.columns if column.endswith("_ts") or column in {"event_ts", "snapshot_ts", "task_ts", "action_ts"}]
        if not timestamp_columns or df.empty:
            continue
        parsed = 0
        total = 0
        for column in timestamp_columns:
            parsed_series = pd.to_datetime(df[column], errors="coerce")
            parsed += int(parsed_series.notna().sum())
            total += int(len(parsed_series.index))
        result[table_name] = round(parsed / total, 4) if total else 0.0
    return result


def estimate_null_ratio(canonical_tables: dict[str, pd.DataFrame], episodes: pd.DataFrame) -> dict[str, float]:
    """Estimate null ratios for the main final tables."""

    result: dict[str, float] = {}
    for table_name, df in {**canonical_tables, "episodes": episodes}.items():
        if df.empty:
            result[table_name] = 0.0
            continue
        result[table_name] = round(float(df.isna().mean().mean()), 4)
    return result


def estimate_device_coverage(dim_device: pd.DataFrame) -> float:
    """Estimate device-domain normalization coverage."""

    if dim_device.empty:
        return 0.0
    known = dim_device["device_domain"].isin({"light", "climate", "fan", "switch", "cover", "media_player", "vacuum", "lock", "sensor", "appliance"}).sum()
    return round(float(known) / float(len(dim_device.index)), 4)


def estimate_action_coverage(action_items: pd.DataFrame) -> float:
    """Estimate action normalization coverage."""

    if action_items.empty:
        return 0.0
    known = action_items["service_name_norm"].isin({"turn_on", "turn_off", "toggle", "set_temperature", "set_humidity", "set_brightness", "open", "close", "lock", "unlock", "play", "pause", "stop", "custom"}).sum()
    return round(float(known) / float(len(action_items.index)), 4)


def estimate_split_leakage(episodes: pd.DataFrame) -> dict[str, Any]:
    """Estimate split leakage by home and user keys."""

    result = {"home_multi_split_count": 0, "user_multi_split_count": 0}
    if episodes.empty:
        return result
    for column, target_key in [("home_sk", "home_multi_split_count"), ("user_sk", "user_multi_split_count")]:
        leakage = episodes.groupby(column)["split"].nunique(dropna=False)
        result[target_key] = int((leakage > 1).sum())
    return result
