from pathlib import Path
import json
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datahub.io import dataframe_to_parquet
from app.datahub.normalize import flatten_actions, maybe_parse_json_string, text_candidates
from app.datahub.schemas import build_action_t, build_sample_t, build_state_t, build_task_t
from scripts._data_common import infer_candidate_devices, log, processed_dataset_dir, raw_dataset_dir, read_any_table


def _extract_slots(row: dict[str, Any]) -> dict[str, Any]:
    slots = row.get("parsed_slots")
    if isinstance(slots, dict):
        return slots
    output_text = row.get("output")
    if isinstance(output_text, str) and output_text.strip():
        try:
            payload = json.loads(output_text)
            if isinstance(payload, dict):
                slot_map = {item.get("name"): item.get("normValue") or item.get("value") for item in payload.get("slots", []) if isinstance(item, dict)}
                slot_map["intent"] = payload.get("intent")
                return slot_map
        except json.JSONDecodeError:
            pass
    for key in ("output", "response", "answer", "label", "target"):
        value = maybe_parse_json_string(row.get(key))
        if isinstance(value, dict):
            return value
    return {}


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("zh_commands")
    processed_dir = processed_dataset_dir("zh_commands")
    utterances: list[dict[str, Any]] = []
    parsed_tasks: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for dataset_dir in [path for path in raw_dir.iterdir() if path.is_dir()]:
        structured_files = [path for path in dataset_dir.rglob("*") if path.is_file() and path.suffix.lower() in {".parquet", ".json", ".jsonl", ".csv"}]
        for file_path in structured_files:
            try:
                df = read_any_table(file_path)
            except Exception as exc:
                log(f"Skipping unreadable zh_commands file {file_path}: {exc}")
                continue
            for row in df.to_dict(orient="records"):
                raw_text = text_candidates(
                    row,
                    ["text", "instruction", "input", "query", "sentence", "utterance"],
                )
                if not raw_text:
                    continue
                slots = _extract_slots(row)
                task = build_task_t(
                    timestamp=row.get("timestamp"),
                    task_source="user_nl",
                    raw_text=raw_text,
                    parsed_slots=slots,
                    trigger={"type": "voice", "detail": slots.get("datetime") or slots.get("schedule")},
                    target_devices_hint=[item for item in [slots.get("device"), slots.get("entity_id"), slots.get("room")] if item],
                    source_dataset="zh_commands",
                )
                actions = flatten_actions(
                    slots.get("actions")
                    or {
                        "device_id": slots.get("device") or slots.get("entity_id") or "",
                        "service": slots.get("action") or slots.get("insType") or slots.get("intent") or "",
                        "arguments": {
                            "attribute": slots.get("attribute"),
                            "attr": slots.get("attr"),
                            "value": slots.get("value"),
                            "attrValue": slots.get("attrValue"),
                            "room": slots.get("room"),
                            "datetime": slots.get("datetime") or slots.get("datatime"),
                            "delay": slots.get("delay"),
                        },
                    }
                )
                action_t = build_action_t(
                    task_id=task["task_id"],
                    timestamp=task["timestamp"],
                    actions=actions,
                    source_dataset="zh_commands",
                    action_reason_type="label" if actions else "inferred",
                )
                utterances.append(
                    {
                        "raw_text": raw_text,
                        "source_file": str(file_path.relative_to(raw_dir)),
                        "parsed_slots": slots,
                    }
                )
                parsed_tasks.append(task)
                samples.append(
                    build_sample_t(
                        state=build_state_t(
                            home_id=str(row.get("home_id") or "zh_home"),
                            timestamp=task["timestamp"],
                            sensor_events=[],
                            device_states={},
                            occupancy=None,
                            activity_hint=slots.get("intent") or slots.get("action"),
                            environment={},
                            source_dataset="zh_commands",
                        ),
                        task=task,
                        target_action=action_t,
                        candidate_devices=infer_candidate_devices(actions, slots),
                        source_dataset="zh_commands",
                        weak_supervision=not bool(actions),
                    )
                )

    dataframe_to_parquet(pd.DataFrame(utterances), processed_dir / "utterances.parquet")
    dataframe_to_parquet(pd.DataFrame(parsed_tasks).drop_duplicates(subset=["task_id"]), processed_dir / "parsed_tasks.parquet")
    dataframe_to_parquet(pd.DataFrame(samples).drop_duplicates(subset=["sample_id"]), processed_dir / "samples.parquet")
    log(f"Processed zh_commands dataset with {len(samples)} samples.")
