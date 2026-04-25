#!/usr/bin/env python3
"""Run fusion-only baseline comparison on the offline warehouse datasets."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.baselines import build_fusion_dataset_baseline_specs
from app.evaluation.dataset_runner import load_evaluation_rows
from app.evaluation.fusion_baseline_runner import build_fusion_baseline_comparison_report
from app.storage.file_store import FileStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare runnable baselines on fusion-only warehouse samples.")
    parser.add_argument("--episodes-path", default=str(PROJECT_ROOT / "data_processed/episodes.parquet"))
    parser.add_argument("--states-path", default=str(PROJECT_ROOT / "data_processed/fact_state_snapshot.parquet"))
    parser.add_argument("--tasks-path", default=str(PROJECT_ROOT / "data_processed/fact_task.parquet"))
    parser.add_argument("--split", default="test")
    parser.add_argument("--source-datasets", default="", help="Comma-separated source datasets to keep before fusion filtering.")
    parser.add_argument("--label-qualities", default="", help="Comma-separated label qualities to keep.")
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--sample-per-source", type=int, default=0)
    parser.add_argument("--baseline-ids", default="", help="Comma-separated baseline ids to run.")
    parser.add_argument("--current-primary-memory-backend", default="hybrid", help="Memory backend for the current program row.")
    parser.add_argument("--llm-enabled", action="store_true", help="Enable LLM-backed baselines when supported.")
    parser.add_argument("--output-dir", default=str(PROJECT_ROOT / "outputs" / "fusion_baselines"))
    parser.add_argument("--run-name", default="")
    parser.add_argument("--output-json", default="fusion_baseline_report.json")
    parser.add_argument("--output-csv", default="comparison_table.csv")
    parser.add_argument("--output-md", default="comparison_table.md")
    parser.add_argument("--no-progress", action="store_true")
    parser.add_argument("--no-run-archive", action="store_true")
    return parser.parse_args()


def _split_csv(raw: str) -> list[str] | None:
    values = [item.strip() for item in raw.split(",") if item.strip()]
    return values or None


def _slugify(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip()).strip("-_").lower()
    return text or "run"


def _prepare_output_dirs(base_output_dir: Path, run_name: str, archive_runs: bool) -> tuple[Path, Path]:
    base_output_dir.mkdir(parents=True, exist_ok=True)
    if not archive_runs:
        return base_output_dir, base_output_dir
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir = base_output_dir / f"{timestamp}_{_slugify(run_name or 'fusion-baselines')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return base_output_dir, run_dir


def _resolve_output_path(output_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return output_dir / candidate


def _write_comparison_table_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    args = parse_args()
    output_root, output_dir = _prepare_output_dirs(
        Path(args.output_dir).resolve(),
        run_name=args.run_name,
        archive_runs=not args.no_run_archive,
    )
    file_store = FileStore()
    file_store.ensure_dir(output_dir)

    rows = load_evaluation_rows(
        episodes_path=Path(args.episodes_path),
        states_path=Path(args.states_path),
        tasks_path=Path(args.tasks_path),
        split=args.split or None,
        source_datasets=_split_csv(args.source_datasets),
        label_qualities=_split_csv(args.label_qualities),
        max_samples=args.max_samples or None,
        sample_per_source=args.sample_per_source or None,
    )
    report = build_fusion_baseline_comparison_report(
        rows=rows,
        output_dir=output_dir,
        baseline_ids=_split_csv(args.baseline_ids),
        current_primary_memory_backend=args.current_primary_memory_backend,
        llm_enabled=args.llm_enabled,
        show_progress=not args.no_progress,
    )

    json_path = _resolve_output_path(output_dir, args.output_json)
    csv_path = _resolve_output_path(output_dir, args.output_csv)
    md_path = _resolve_output_path(output_dir, args.output_md)
    file_store.write_json(json_path, report.model_dump(mode="json"))
    _write_comparison_table_csv(
        csv_path,
        [row.model_dump(mode="json") for row in report.comparison_table],
    )
    file_store.write_text(md_path, report.comparison_table_markdown + "\n")
    file_store.write_json(
        output_dir / "available_baselines.json",
        [spec.model_dump(mode="json") for spec in build_fusion_dataset_baseline_specs()],
    )

    print("[fusion-baseline] report")
    print(json.dumps(report.model_dump(mode="json"), indent=2))
    print(f"[fusion-baseline] output root: {output_root}")
    print(f"[fusion-baseline] run dir: {output_dir}")
    print(f"[fusion-baseline] report: {json_path}")
    print(f"[fusion-baseline] comparison csv: {csv_path}")
    print(f"[fusion-baseline] comparison md: {md_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
