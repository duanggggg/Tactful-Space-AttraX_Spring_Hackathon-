#!/usr/bin/env python3
"""Prepare web-origin records into the same canonical dataset structure as fusion data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datasets.unified_adapter import build_unified_dataset_bundle


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize placeholder web records into the canonical bundle format.")
    parser.add_argument("--input", default=str(PROJECT_ROOT / "data_interim" / "web" / "web_records.jsonl"))
    parser.add_argument("--output", default=str(PROJECT_ROOT / "data_processed" / "web" / "canonical_preview.jsonl"))
    return parser.parse_args()


def _load_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def main() -> int:
    args = parse_args()
    input_path = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows = _load_rows(input_path)
    bundles = []
    for index, row in enumerate(rows, start=1):
        bundle = build_unified_dataset_bundle(
            source_dataset=str(row.get("source_dataset") or "web_collected"),
            home_id=str(row.get("home_id") or "web-home-1"),
            timestamp=row.get("timestamp"),
            task_source=str(row.get("task_source") or "user_nl"),
            raw_text=str(row.get("raw_text") or ""),
            actions=row.get("actions") or [],
            sensor_events=row.get("sensor_events"),
            device_states=row.get("device_states"),
            occupancy=row.get("occupancy"),
            activity_hint=row.get("activity_hint"),
            environment=row.get("environment"),
            parsed_slots=row.get("parsed_slots"),
            trigger=row.get("trigger"),
            target_devices_hint=row.get("target_devices_hint"),
            action_reason_type=str(row.get("action_reason_type") or "weak"),
            candidate_devices=row.get("candidate_devices"),
            weak_supervision=bool(row.get("weak_supervision", True)),
            recent_history=row.get("recent_history"),
        )
        bundles.append(
            {
                "row_index": index,
                "source_profile": bundle.source_profile.__dict__,
                "state_t": bundle.state_t,
                "task_t": bundle.task_t,
                "action_t": bundle.action_t,
                "sample_t": bundle.sample_t,
                "task_request": bundle.to_task_request().model_dump(mode="json"),
            }
        )

    with output_path.open("w", encoding="utf-8") as handle:
        for bundle in bundles:
            handle.write(json.dumps(bundle, ensure_ascii=False))
            handle.write("\n")

    print(f"[web-scaffold] input rows: {len(rows)}")
    print(f"[web-scaffold] wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
