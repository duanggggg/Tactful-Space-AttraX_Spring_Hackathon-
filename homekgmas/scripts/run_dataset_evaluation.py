#!/usr/bin/env python3
"""Run offline evaluation on warehouse episode samples."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.evaluation.dataset_runner import build_dataset_eval_report, load_evaluation_rows
from app.storage.file_store import FileStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate the current orchestration pipeline on episode-level warehouse samples.")
    parser.add_argument("--episodes-path", default=str(PROJECT_ROOT / "data_processed/episodes.parquet"))
    parser.add_argument("--states-path", default=str(PROJECT_ROOT / "data_processed/fact_state_snapshot.parquet"))
    parser.add_argument("--tasks-path", default=str(PROJECT_ROOT / "data_processed/fact_task.parquet"))
    parser.add_argument("--split", default="test", help="Dataset split to evaluate. Use empty string to disable split filtering.")
    parser.add_argument("--source-datasets", default="", help="Comma-separated source datasets to keep.")
    parser.add_argument("--label-qualities", default="", help="Comma-separated label qualities to keep.")
    parser.add_argument("--max-samples", type=int, default=0, help="Maximum number of samples to evaluate. 0 means no cap.")
    parser.add_argument("--sample-per-source", type=int, default=0, help="Cap samples per source dataset before the global cap. 0 disables.")
    parser.add_argument("--primary-memory-backend", default="none", help="Memory backend used during evaluation.")
    parser.add_argument("--llm-enabled", action="store_true", help="Enable LLM-backed agent proposals during evaluation.")
    parser.add_argument(
        "--output-dir",
        default=str(PROJECT_ROOT / "outputs" / "dataset_eval"),
        help="Evaluation output root directory.",
    )
    parser.add_argument("--run-name", default="", help="Optional human-readable label for this run.")
    parser.add_argument(
        "--output-json",
        default="report.json",
        help="Evaluation report JSON file name, relative to output-dir unless absolute.",
    )
    parser.add_argument(
        "--output-csv",
        default="records.csv",
        help="Per-sample evaluation CSV file name, relative to output-dir unless absolute.",
    )
    parser.add_argument(
        "--no-progress",
        action="store_true",
        help="Disable tqdm progress bars and use plain logs only.",
    )
    parser.add_argument(
        "--no-run-archive",
        action="store_true",
        help="Write directly into output-dir instead of creating a timestamped run subdirectory.",
    )
    return parser.parse_args()


def _resolve_output_path(output_dir: Path, raw_path: str) -> Path:
    candidate = Path(raw_path)
    if candidate.is_absolute():
        return candidate
    return output_dir / candidate


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
    run_dir = base_output_dir / f"{timestamp}_{_slugify(run_name or 'dataset-eval')}"
    run_dir.mkdir(parents=True, exist_ok=True)
    return base_output_dir, run_dir


def _append_run_manifest(manifest_path: Path, entry: dict) -> None:
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=True))
        handle.write("\n")


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
    print(f"[dataset-eval] loaded {len(rows)} row(s) for evaluation")
    report = build_dataset_eval_report(
        rows=rows,
        output_dir=output_dir,
        primary_memory_backend=args.primary_memory_backend,
        llm_enabled=args.llm_enabled,
        show_progress=not args.no_progress,
    )

    json_path = _resolve_output_path(output_dir, args.output_json)
    csv_path = _resolve_output_path(output_dir, args.output_csv)
    file_store.write_json(json_path, report.model_dump(mode="json"))
    pd.DataFrame([record.model_dump(mode="json") for record in report.records]).to_csv(csv_path, index=False)

    run_manifest = {
        "run_id": output_dir.name,
        "generated_at": report.generated_at,
        "run_name": args.run_name or output_dir.name,
        "output_root": str(output_root),
        "run_dir": str(output_dir),
        "report_path": str(json_path),
        "records_path": str(csv_path),
        "config": {
            "episodes_path": str(Path(args.episodes_path).resolve()),
            "states_path": str(Path(args.states_path).resolve()),
            "tasks_path": str(Path(args.tasks_path).resolve()),
            "split": args.split,
            "source_datasets": _split_csv(args.source_datasets),
            "label_qualities": _split_csv(args.label_qualities),
            "max_samples": args.max_samples,
            "sample_per_source": args.sample_per_source,
            "primary_memory_backend": args.primary_memory_backend,
            "llm_enabled": args.llm_enabled,
        },
        "summary": report.summary.model_dump(mode="json"),
    }
    file_store.write_json(output_dir / "run_manifest.json", run_manifest)
    file_store.write_json(output_root / "latest_run.json", run_manifest)
    _append_run_manifest(output_root / "runs_manifest.jsonl", run_manifest)

    print("[dataset-eval] summary")
    print(json.dumps(report.summary.model_dump(mode="json"), indent=2))
    print(f"[dataset-eval] per-source keys: {list(report.by_source_dataset.keys())}")
    print(f"[dataset-eval] run dir: {output_dir}")
    print(f"[dataset-eval] report: {json_path}")
    print(f"[dataset-eval] records: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
