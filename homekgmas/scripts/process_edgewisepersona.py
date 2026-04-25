from pathlib import Path
import json
import sys
from typing import Any

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datahub.io import dataframe_to_parquet
from app.datahub.normalize import normalize_domain
from app.datahub.schemas import build_action_t, build_sample_t, build_state_t, build_task_t
from scripts._data_common import infer_candidate_devices, log, processed_dataset_dir, raw_dataset_dir


def _infer_service(arguments: dict[str, Any]) -> str:
    if "temperature" in arguments:
        return "set_temperature"
    if "brightness" in arguments:
        return "set_brightness"
    if "volume" in arguments and len(arguments) == 1:
        return "custom"
    if arguments:
        return "custom"
    return "turn_on"


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("edgewisepersona")
    processed_dir = processed_dataset_dir("edgewisepersona")
    personas: list[dict[str, Any]] = []
    routines: list[dict[str, Any]] = []
    sessions: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for dataset_dir in [path for path in raw_dir.iterdir() if path.is_dir()]:
        for file_path in dataset_dir.rglob("*.jsonl"):
            lines = [json.loads(line) for line in file_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            lower_name = file_path.name.lower()
            if "character" in lower_name:
                for index, item in enumerate(lines):
                    personas.append(
                        {
                            "persona_id": f"persona_{index}",
                            "character": item.get("character"),
                        }
                    )
            elif "routine" in lower_name:
                for persona_index, item in enumerate(lines):
                    for routine_index, routine in enumerate(item.get("routines", [])):
                        routines.append(
                            {
                                "persona_id": f"persona_{persona_index}",
                                "routine_id": f"routine_{persona_index}_{routine_index}",
                                "triggers": routine.get("triggers"),
                                "actions": routine.get("actions"),
                            }
                        )
            elif "session" in lower_name:
                for persona_index, item in enumerate(lines):
                    for session in item.get("sessions", []):
                        sessions.append(
                            {
                                "persona_id": f"persona_{persona_index}",
                                "session_id": session.get("session_id"),
                                "meta": session.get("meta"),
                                "messages": session.get("messages"),
                                "applied_routines": session.get("applied_routines"),
                            }
                        )

    persona_df = pd.DataFrame(personas)
    routine_df = pd.DataFrame(routines)
    session_df = pd.DataFrame(sessions)

    routine_lookup = {
        str(row.get("routine_id") or index): row.to_dict()
        for index, row in routine_df.iterrows()
    }
    for index, row in session_df.iterrows():
        row_dict = row.to_dict()
        messages = row_dict.get("messages") or []
        user_messages = [item.get("text") for item in messages if isinstance(item, dict) and item.get("role") == "user"]
        raw_text = " ".join(message for message in user_messages if isinstance(message, str) and message.strip()).strip()
        raw_text = raw_text or f"Session {index}"
        routine_ids = row_dict.get("applied_routines") or []
        if isinstance(routine_ids, str):
            routine_ids = [routine_ids]
        routine_actions: list[dict[str, Any]] = []
        for routine_id in routine_ids:
            routine_row = routine_lookup.get(f"routine_{row_dict.get('persona_id', '').split('_')[-1]}_{routine_id}")
            if routine_row is None:
                routine_row = routine_lookup.get(str(routine_id))
            if routine_row:
                routine_action_payload = routine_row.get("actions") or {}
                for device_name, action_payload in routine_action_payload.items():
                    if action_payload is None:
                        continue
                    if isinstance(action_payload, dict):
                        routine_actions.append(
                            {
                                "device_id": device_name,
                                "domain": normalize_domain(device_name),
                                "service": _infer_service(action_payload),
                                "arguments": action_payload,
                            }
                        )
        if not routine_actions:
            routine_actions = []
        task = build_task_t(
            timestamp=None,
            task_source="routine" if routine_ids else "user_nl",
            raw_text=raw_text,
            parsed_slots={
                "persona_id": row_dict.get("persona_id") or row_dict.get("user_id"),
                "routine_ids": routine_ids,
            },
            trigger={"type": "habit" if routine_ids else "event", "detail": row_dict.get("meta") or routine_ids or None},
            target_devices_hint=[action["device_id"] for action in routine_actions if action["device_id"]],
            source_dataset="edgewisepersona",
        )
        action_t = build_action_t(
            task_id=task["task_id"],
            timestamp=task["timestamp"],
            actions=routine_actions,
            source_dataset="edgewisepersona",
            action_reason_type="routine" if routine_ids else "label",
        )
        samples.append(
            build_sample_t(
                state=build_state_t(
                    home_id=str(row_dict.get("home_id") or row_dict.get("persona_id") or "edgewise_home"),
                    timestamp=task["timestamp"],
                    sensor_events=[],
                    device_states=row_dict.get("device_states") or {},
                    occupancy=row_dict.get("occupancy"),
                    activity_hint=(row_dict.get("meta") or {}).get("time_of_day"),
                    environment=row_dict.get("meta") or {},
                    source_dataset="edgewisepersona",
                ),
                task=task,
                target_action=action_t,
                candidate_devices=infer_candidate_devices(routine_actions, row_dict),
                source_dataset="edgewisepersona",
                weak_supervision=not bool(routine_actions),
            )
        )

    dataframe_to_parquet(persona_df, processed_dir / "personas.parquet")
    dataframe_to_parquet(routine_df, processed_dir / "routines.parquet")
    dataframe_to_parquet(session_df, processed_dir / "sessions.parquet")
    dataframe_to_parquet(pd.DataFrame(samples).drop_duplicates(subset=["sample_id"]), processed_dir / "samples.parquet")
    log(f"Processed EdgeWisePersona dataset with {len(samples)} samples.")
