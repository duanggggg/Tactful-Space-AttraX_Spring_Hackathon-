"""Validation helpers for built smart-home warehouse datasets."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

from app.datahub.io import DATA_PROCESSED_DIR, REPORTS_DIR, write_json
from app.datahub.warehouse_schema import (
    ACTION_ENUM,
    CANDIDATE_SOURCE_ENUM,
    DEVICE_DOMAIN_ENUM,
    LABEL_QUALITY_ENUM,
    TABLE_SPECS,
    TASK_SOURCE_ENUM,
)


CORE_PROCESSED_TABLES = [
    "dim_home",
    "dim_area",
    "dim_device",
    "dim_entity",
    "dim_user",
    "fact_state_snapshot",
    "fact_task",
    "fact_action_set",
    "fact_action_item",
    "bridge_state_sensor_event",
    "bridge_task_candidate_device",
    "bridge_episode_source",
    "synthetic_discussion",
    "episodes",
]

REQUIRED_REPORTS = [
    "data_profile.md",
    "data_gaps.md",
    "data_quality.json",
]


@dataclass
class ValidationCheck:
    """One dataset validation result."""

    name: str
    passed: bool
    detail: str
    severity: str = "error"


def _parquet_columns(path: Path) -> list[str]:
    """Read parquet column names without loading the table into memory."""

    return pq.read_schema(path).names


def _parquet_rows(path: Path) -> int:
    """Read parquet row count from metadata."""

    return int(pq.ParquetFile(path).metadata.num_rows)


def _load_columns(path: Path, columns: list[str]) -> pd.DataFrame:
    """Load only the selected parquet columns."""

    return pd.read_parquet(path, columns=columns)


def _parse_json_like(value: Any) -> Any:
    """Parse a JSON string or pass through nested objects."""

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


def _invalid_enum_values(series: pd.Series, allowed: set[str]) -> list[str]:
    """Return sorted invalid enum values from one column."""

    values = {
        str(value)
        for value in series.dropna().unique().tolist()
        if str(value) not in allowed
    }
    return sorted(values)


def _duplicate_count(path: Path, columns: list[str]) -> int:
    """Count duplicates for the selected key columns."""

    if not columns:
        return 0
    df = _load_columns(path, columns)
    return int(df.duplicated().sum())


def _missing_reference_count(left: pd.Series, right: pd.Series) -> int:
    """Count foreign-key values missing from the target key set."""

    left_non_null = left.dropna()
    if left_non_null.empty:
        return 0
    right_unique = pd.Index(right.dropna().unique())
    return int((~left_non_null.isin(right_unique)).sum())


def _missing_reference_ratio(left: pd.Series, right: pd.Series) -> float:
    """Count foreign-key miss ratio against non-null source rows."""

    left_non_null = left.dropna()
    if left_non_null.empty:
        return 0.0
    missing_count = _missing_reference_count(left_non_null, right)
    return float(missing_count) / float(len(left_non_null.index))


def _json_sample_errors(path: Path, column: str, sample_size: int) -> list[str]:
    """Return JSON parse errors for a sampled parquet column."""

    df = _load_columns(path, [column]).head(sample_size)
    errors: list[str] = []
    for index, value in enumerate(df[column].tolist()):
        try:
            parsed = _parse_json_like(value)
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(f"row={index}: {exc}")
            continue
        if parsed is None:
            errors.append(f"row={index}: empty payload")
    return errors


def _device_coverage(dim_device: pd.DataFrame) -> float:
    allowed = set(DEVICE_DOMAIN_ENUM) - {"other"}
    if dim_device.empty:
        return 0.0
    return round(float(dim_device["device_domain"].isin(allowed).sum()) / float(len(dim_device.index)), 4)


def _action_coverage(action_item: pd.DataFrame) -> float:
    allowed = set(ACTION_ENUM)
    if action_item.empty:
        return 0.0
    return round(float(action_item["service_name_norm"].isin(allowed).sum()) / float(len(action_item.index)), 4)


def _split_leakage(episodes: pd.DataFrame) -> dict[str, int]:
    result = {"home_multi_split_count": 0, "user_multi_split_count": 0}
    if episodes.empty:
        return result
    for column, key in [("home_sk", "home_multi_split_count"), ("user_sk", "user_multi_split_count")]:
        leakage = episodes.groupby(column)["split"].nunique(dropna=False)
        result[key] = int((leakage > 1).sum())
    return result


def validate_warehouse_outputs(
    *,
    processed_root: Path | None = None,
    reports_root: Path | None = None,
    sample_size: int = 128,
    min_episode_count: int = 1000,
    min_device_coverage: float = 0.60,
    min_action_coverage: float = 0.95,
    max_home_multi_split_count: int = 10,
    max_user_multi_split_count: int = 10,
) -> dict[str, Any]:
    """Validate built warehouse outputs and return a machine-readable summary."""

    processed_root = (processed_root or DATA_PROCESSED_DIR).resolve()
    reports_root = (reports_root or REPORTS_DIR).resolve()
    checks: list[ValidationCheck] = []
    row_counts: dict[str, int] = {}

    def record(name: str, passed: bool, detail: str, severity: str = "error") -> None:
        checks.append(ValidationCheck(name=name, passed=passed, detail=detail, severity=severity))

    missing_files: list[str] = []
    for table_name in CORE_PROCESSED_TABLES:
        path = processed_root / f"{table_name}.parquet"
        exists = path.exists()
        record(
            f"file_exists:{table_name}",
            exists,
            f"{path}" if exists else f"missing {path}",
        )
        if exists:
            row_counts[table_name] = _parquet_rows(path)
        else:
            missing_files.append(table_name)

    for report_name in REQUIRED_REPORTS:
        path = reports_root / report_name
        record(
            f"report_exists:{report_name}",
            path.exists(),
            f"{path}" if path.exists() else f"missing {path}",
            severity="warning",
        )

    if missing_files:
        return {
            "passed": False,
            "summary": {
                "processed_root": str(processed_root),
                "reports_root": str(reports_root),
                "row_counts": row_counts,
            },
            "checks": [check.__dict__ for check in checks],
        }

    for table_name in CORE_PROCESSED_TABLES:
        path = processed_root / f"{table_name}.parquet"
        expected = TABLE_SPECS[table_name].columns
        actual = _parquet_columns(path)
        record(
            f"schema:{table_name}",
            actual == expected,
            f"expected={expected}, actual={actual}",
        )

    for table_name in ["fact_state_snapshot", "fact_task", "fact_action_set", "fact_action_item", "episodes"]:
        record(
            f"row_count:{table_name}",
            row_counts.get(table_name, 0) > 0,
            f"rows={row_counts.get(table_name, 0)}",
        )

    for table_name in ["dim_home", "dim_area", "dim_device", "dim_entity", "dim_user", "fact_task", "fact_action_set", "fact_action_item", "episodes"]:
        path = processed_root / f"{table_name}.parquet"
        pk = TABLE_SPECS[table_name].primary_key
        duplicates = _duplicate_count(path, pk)
        record(
            f"primary_key_unique:{table_name}",
            duplicates == 0,
            f"duplicates={duplicates} on {pk}",
        )

    dim_device = _load_columns(processed_root / "dim_device.parquet", ["device_sk", "device_domain"])
    dim_entity = _load_columns(processed_root / "dim_entity.parquet", ["entity_sk", "device_sk"])
    fact_state_snapshot = _load_columns(processed_root / "fact_state_snapshot.parquet", ["state_id"])
    fact_task = _load_columns(processed_root / "fact_task.parquet", ["task_id", "task_source", "label_quality"])
    fact_action_set = _load_columns(processed_root / "fact_action_set.parquet", ["action_set_id", "task_id", "label_quality"])
    fact_action_item = _load_columns(
        processed_root / "fact_action_item.parquet",
        ["action_item_id", "action_set_id", "device_sk", "entity_sk", "device_domain", "service_name_norm"],
    )
    candidate_bridge = _load_columns(
        processed_root / "bridge_task_candidate_device.parquet",
        ["task_id", "device_sk", "candidate_source", "candidate_rank", "candidate_score"],
    )
    synthetic_discussion = _load_columns(
        processed_root / "synthetic_discussion.parquet",
        ["discussion_id", "task_id", "device_sk", "proposal_type", "is_synthetic"],
    )
    episodes = _load_columns(
        processed_root / "episodes.parquet",
        ["sample_id", "home_sk", "user_sk", "state_id", "task_id", "action_set_id", "label_quality", "split", "candidate_devices_json", "target_actions_json", "synthetic_discussion_json", "source_mix_json"],
    )

    fk_checks = [
        ("episodes.state_id->fact_state_snapshot", episodes["state_id"], fact_state_snapshot["state_id"], 0.0, "error"),
        ("episodes.task_id->fact_task", episodes["task_id"], fact_task["task_id"], 0.0, "error"),
        ("episodes.action_set_id->fact_action_set", episodes["action_set_id"], fact_action_set["action_set_id"], 0.0, "error"),
        ("fact_action_set.task_id->fact_task", fact_action_set["task_id"], fact_task["task_id"], 0.0, "error"),
        ("fact_action_item.action_set_id->fact_action_set", fact_action_item["action_set_id"], fact_action_set["action_set_id"], 0.0, "error"),
        ("fact_action_item.device_sk->dim_device", fact_action_item["device_sk"], dim_device["device_sk"], 0.001, "warning"),
        ("fact_action_item.entity_sk->dim_entity", fact_action_item["entity_sk"], dim_entity["entity_sk"], 0.001, "warning"),
        ("bridge_task_candidate_device.task_id->fact_task", candidate_bridge["task_id"], fact_task["task_id"], 0.0, "error"),
        ("bridge_task_candidate_device.device_sk->dim_device", candidate_bridge["device_sk"], dim_device["device_sk"], 0.0, "error"),
        ("synthetic_discussion.task_id->fact_task", synthetic_discussion["task_id"], fact_task["task_id"], 0.0, "error"),
        ("synthetic_discussion.device_sk->dim_device", synthetic_discussion["device_sk"], dim_device["device_sk"], 0.0, "error"),
    ]
    for name, left, right, max_missing_ratio, severity in fk_checks:
        missing = _missing_reference_count(left, right)
        ratio = _missing_reference_ratio(left, right)
        record(
            name,
            ratio <= max_missing_ratio,
            f"missing_reference_count={missing}, missing_ratio={ratio:.6f}, max_allowed_ratio={max_missing_ratio:.6f}",
            severity=severity,
        )

    enum_checks = [
        ("episodes.split", episodes["split"], {"train", "valid", "test"}),
        ("episodes.label_quality", episodes["label_quality"], set(LABEL_QUALITY_ENUM)),
        ("fact_task.task_source", fact_task["task_source"], set(TASK_SOURCE_ENUM)),
        ("fact_task.label_quality", fact_task["label_quality"], set(LABEL_QUALITY_ENUM)),
        ("fact_action_set.label_quality", fact_action_set["label_quality"], set(LABEL_QUALITY_ENUM)),
        ("dim_device.device_domain", dim_device["device_domain"], set(DEVICE_DOMAIN_ENUM)),
        ("fact_action_item.device_domain", fact_action_item["device_domain"], set(DEVICE_DOMAIN_ENUM)),
        ("fact_action_item.service_name_norm", fact_action_item["service_name_norm"], set(ACTION_ENUM)),
        ("bridge_task_candidate_device.candidate_source", candidate_bridge["candidate_source"], set(CANDIDATE_SOURCE_ENUM)),
    ]
    for name, series, allowed in enum_checks:
        invalid = _invalid_enum_values(series, allowed)
        record(name, not invalid, f"invalid={invalid}")

    record(
        "episodes.min_count",
        row_counts["episodes"] >= min_episode_count,
        f"episodes={row_counts['episodes']}, min_required={min_episode_count}",
    )

    strong_ratio = float((episodes["label_quality"] == "strong").mean()) if not episodes.empty else 0.0
    record(
        "episodes.strong_ratio",
        strong_ratio >= 0.50,
        f"strong_ratio={strong_ratio:.4f}",
        severity="warning",
    )

    device_coverage = _device_coverage(dim_device)
    action_coverage = _action_coverage(fact_action_item)
    record(
        "device_domain_coverage",
        device_coverage >= min_device_coverage,
        f"coverage={device_coverage:.4f}, min_required={min_device_coverage:.4f}",
        severity="warning",
    )
    record(
        "action_service_coverage",
        action_coverage >= min_action_coverage,
        f"coverage={action_coverage:.4f}, min_required={min_action_coverage:.4f}",
    )

    leakage = _split_leakage(episodes)
    record(
        "split_leakage.home",
        leakage["home_multi_split_count"] <= max_home_multi_split_count,
        f"home_multi_split_count={leakage['home_multi_split_count']}, max_allowed={max_home_multi_split_count}",
        severity="warning",
    )
    record(
        "split_leakage.user",
        leakage["user_multi_split_count"] <= max_user_multi_split_count,
        f"user_multi_split_count={leakage['user_multi_split_count']}, max_allowed={max_user_multi_split_count}",
        severity="warning",
    )

    json_columns = [
        "candidate_devices_json",
        "target_actions_json",
        "synthetic_discussion_json",
        "source_mix_json",
    ]
    for column in json_columns:
        errors = _json_sample_errors(processed_root / "episodes.parquet", column, sample_size)
        non_empty = 0
        for value in episodes[column].head(sample_size).tolist():
            try:
                parsed = _parse_json_like(value)
            except Exception:
                continue
            if parsed not in (None, [], {}):
                non_empty += 1
        record(
            f"json_parse:{column}",
            not errors,
            f"errors={errors[:5]}",
        )
        record(
            f"json_non_empty:{column}",
            non_empty > 0,
            f"non_empty_samples={non_empty}/{min(sample_size, len(episodes.index))}",
            severity="warning",
        )

    passed = not any((not check.passed and check.severity == "error") for check in checks)
    return {
        "passed": passed,
        "summary": {
            "processed_root": str(processed_root),
            "reports_root": str(reports_root),
            "row_counts": row_counts,
            "device_domain_coverage": device_coverage,
            "action_service_coverage": action_coverage,
            "split_leakage": leakage,
            "strong_ratio": round(strong_ratio, 4),
        },
        "checks": [check.__dict__ for check in checks],
    }


def write_validation_report(report_path: Path, payload: dict[str, Any]) -> None:
    """Persist one validation payload to JSON."""

    write_json(report_path, payload)
