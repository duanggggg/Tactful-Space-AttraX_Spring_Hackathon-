"""Quality checks and reporting for processed datasets."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

import pandas as pd

from app.datahub.io import REPORTS_DIR, append_markdown_section, dataframe_to_csv, write_json


def _null_ratio(df: pd.DataFrame, column: str) -> float:
    if column not in df.columns or len(df.index) == 0:
        return 0.0
    return round(float(df[column].isna().mean()), 4)


def profile_processed_tables(processed_root: Path) -> tuple[dict[str, Any], pd.DataFrame]:
    """Build a quality summary over processed parquet files."""

    quality: dict[str, Any] = {
        "generated_at": pd.Timestamp.utcnow().isoformat(),
        "datasets": {},
    }
    rows: list[dict[str, Any]] = []
    for parquet_path in sorted(processed_root.rglob("*.parquet")):
        dataset_name = parquet_path.parent.name
        try:
            df = pd.read_parquet(parquet_path)
        except Exception as exc:
            entry = quality["datasets"].setdefault(dataset_name, {"tables": {}})
            entry["tables"][parquet_path.stem] = {
                "row_count": None,
                "column_count": None,
                "timestamp_parse_rate": None,
                "empty_raw_text_ratio": None,
                "duplicate_row_count": None,
                "read_error": str(exc),
            }
            continue
        row_count = int(len(df.index))
        rows.append(
            {
                "source_dataset": dataset_name,
                "table_name": parquet_path.stem,
                "row_count": row_count,
            }
        )
        entry = quality["datasets"].setdefault(dataset_name, {"tables": {}})
        entry["tables"][parquet_path.stem] = {
            "row_count": row_count,
            "column_count": len(df.columns),
            "timestamp_parse_rate": round(
                1.0 - _null_ratio(df, "timestamp"),
                4,
            )
            if "timestamp" in df.columns
            else None,
            "empty_raw_text_ratio": _null_ratio(df, "raw_text"),
            "duplicate_row_count": int(df.duplicated().sum()),
        }

    sample_counts = pd.DataFrame(rows)
    if not sample_counts.empty:
        counts_by_dataset = Counter(sample_counts["source_dataset"])
        quality["dataset_table_count"] = dict(counts_by_dataset)
    return quality, sample_counts


def _coverage_from_samples(samples_df: pd.DataFrame) -> dict[str, Any]:
    if samples_df.empty:
        return {
            "device_domain_mapping_coverage": 0.0,
            "action_mapping_coverage": 0.0,
            "source_dataset_distribution": {},
            "split_leakage": {},
        }

    domain_total = 0
    domain_known = 0
    service_total = 0
    service_known = 0
    for row in samples_df.to_dict(orient="records"):
        target_action = row.get("target_action") or {}
        if isinstance(target_action, str):
            try:
                target_action = json.loads(target_action)
            except json.JSONDecodeError:
                target_action = {}
        actions = target_action.get("actions", []) if isinstance(target_action, dict) else []
        for action in actions:
            if not isinstance(action, dict):
                continue
            domain_total += 1
            service_total += 1
            if str(action.get("domain", "")) not in {"", "other"}:
                domain_known += 1
            if str(action.get("service", "")) not in {"", "custom"}:
                service_known += 1

    split_leakage: dict[str, Any] = {}
    if {"split", "state"}.issubset(samples_df.columns):
        home_split: dict[str, set[str]] = {}
        for row in samples_df.to_dict(orient="records"):
            state = row.get("state") or {}
            if isinstance(state, str):
                try:
                    state = json.loads(state)
                except json.JSONDecodeError:
                    state = {}
            home_id = str(state.get("home_id") or "")
            if not home_id:
                continue
            home_split.setdefault(home_id, set()).add(str(row.get("split")))
        leaked = {home_id: sorted(list(splits)) for home_id, splits in home_split.items() if len(splits) > 1}
        split_leakage["home_id_multi_split_count"] = len(leaked)
        split_leakage["home_id_examples"] = dict(list(leaked.items())[:10])

    return {
        "device_domain_mapping_coverage": round(domain_known / domain_total, 4) if domain_total else 0.0,
        "action_mapping_coverage": round(service_known / service_total, 4) if service_total else 0.0,
        "source_dataset_distribution": samples_df["source_dataset"].value_counts(dropna=False).to_dict()
        if "source_dataset" in samples_df.columns
        else {},
        "split_leakage": split_leakage,
    }


def write_quality_reports(processed_root: Path) -> None:
    """Write markdown, JSON, and CSV quality reports."""

    quality, sample_counts = profile_processed_tables(processed_root)
    unified_paths = sorted(processed_root.glob("unified_samples_*.parquet"))
    if unified_paths:
        unified = pd.concat([pd.read_parquet(path) for path in unified_paths], ignore_index=True)
        quality["unified_samples"] = {
            "row_count": int(len(unified.index)),
            **_coverage_from_samples(unified),
        }
    write_json(REPORTS_DIR / "data_quality.json", quality)
    dataframe_to_csv(sample_counts, REPORTS_DIR / "sample_counts.csv")

    profile_path = REPORTS_DIR / "data_profile.md"
    profile_path.write_text("# Data Profile\n\n", encoding="utf-8")
    for dataset_name, payload in quality.get("datasets", {}).items():
        lines = [
            f"{table}: {table_payload['row_count']} rows, {table_payload['column_count']} columns"
            for table, table_payload in payload.get("tables", {}).items()
        ]
        append_markdown_section(profile_path, dataset_name, lines or ["No processed tables yet."])
    if "unified_samples" in quality:
        unified_lines = [
            f"row_count: {quality['unified_samples']['row_count']}",
            f"device_domain_mapping_coverage: {quality['unified_samples']['device_domain_mapping_coverage']}",
            f"action_mapping_coverage: {quality['unified_samples']['action_mapping_coverage']}",
            f"source_dataset_distribution: {quality['unified_samples']['source_dataset_distribution']}",
            f"split_leakage: {quality['unified_samples']['split_leakage']}",
        ]
        append_markdown_section(profile_path, "unified_samples", unified_lines)
