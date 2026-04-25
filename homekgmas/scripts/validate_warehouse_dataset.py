#!/usr/bin/env python3
"""Validate the built smart-home warehouse dataset outputs."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datahub.io import DATA_PROCESSED_DIR, REPORTS_DIR
from app.datahub.validation import validate_warehouse_outputs, write_validation_report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate the generated warehouse dataset and reports.")
    parser.add_argument("--processed-root", default=str(DATA_PROCESSED_DIR), help="Processed parquet directory.")
    parser.add_argument("--reports-root", default=str(REPORTS_DIR), help="Reports directory.")
    parser.add_argument(
        "--output-json",
        default=str(REPORTS_DIR / "dataset_validation_summary.json"),
        help="Validation report output path.",
    )
    parser.add_argument("--sample-size", type=int, default=128, help="Sample size used for JSON payload validation.")
    parser.add_argument("--min-episode-count", type=int, default=1000, help="Minimum expected episode count.")
    parser.add_argument("--min-device-coverage", type=float, default=0.60, help="Minimum acceptable normalized device-domain coverage.")
    parser.add_argument("--min-action-coverage", type=float, default=0.95, help="Minimum acceptable normalized action coverage.")
    parser.add_argument("--max-home-multi-split", type=int, default=10, help="Maximum allowed homes spanning multiple splits.")
    parser.add_argument("--max-user-multi-split", type=int, default=10, help="Maximum allowed users spanning multiple splits.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = validate_warehouse_outputs(
        processed_root=Path(args.processed_root),
        reports_root=Path(args.reports_root),
        sample_size=args.sample_size,
        min_episode_count=args.min_episode_count,
        min_device_coverage=args.min_device_coverage,
        min_action_coverage=args.min_action_coverage,
        max_home_multi_split_count=args.max_home_multi_split,
        max_user_multi_split_count=args.max_user_multi_split,
    )
    write_validation_report(Path(args.output_json), payload)

    checks = payload["checks"]
    failed_errors = [check for check in checks if not check["passed"] and check["severity"] == "error"]
    failed_warnings = [check for check in checks if not check["passed"] and check["severity"] == "warning"]

    print("[dataset-validation] summary")
    print(f"- passed: {payload['passed']}")
    print(f"- processed_root: {payload['summary']['processed_root']}")
    print(f"- episodes: {payload['summary']['row_counts'].get('episodes', 0)}")
    print(f"- device_domain_coverage: {payload['summary'].get('device_domain_coverage', 0.0):.4f}")
    print(f"- action_service_coverage: {payload['summary'].get('action_service_coverage', 0.0):.4f}")
    print(f"- split_leakage: {payload['summary'].get('split_leakage', {})}")
    print(f"- report: {args.output_json}")

    if failed_errors:
        print("[dataset-validation] failed error checks:")
        for check in failed_errors:
            print(f"  - {check['name']}: {check['detail']}")
    if failed_warnings:
        print("[dataset-validation] warning checks:")
        for check in failed_warnings:
            print(f"  - {check['name']}: {check['detail']}")

    return 0 if payload["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
