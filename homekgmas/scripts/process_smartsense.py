from pathlib import Path
import sys
from typing import Any
import zipfile

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datahub.io import dataframe_to_parquet
from app.datahub.normalize import normalize_domain, normalize_service, safe_json, stable_id
from app.datahub.schemas import build_action_t, build_sample_t, build_state_t, build_task_t
from scripts._data_common import log, processed_dataset_dir, raw_dataset_dir


DATASET_NAME = "smartsense"


def _exec_dictionary(source: str) -> dict[str, dict[str, int]]:
    namespace: dict[str, dict[str, int]] = {}
    exec(source, {}, namespace)
    return {key: value for key, value in namespace.items() if isinstance(value, dict)}


def _reverse_mapping(mapping: dict[str, int]) -> dict[int, str]:
    return {value: key for key, value in mapping.items()}


def _sequence_step_to_action(step: list[int], reverse_maps: dict[str, dict[int, str]]) -> dict[str, object]:
    dow = reverse_maps["dayofweek_dict"].get(int(step[0]), f"day:{int(step[0])}")
    hour = reverse_maps["hour_dict"].get(int(step[1]), f"time:{int(step[1])}")
    device_name = reverse_maps["device_dict"].get(int(step[2]), str(int(step[2])))
    device_control = reverse_maps["device_control_dict"].get(int(step[4]), f"{device_name}:unknown")
    service_name = device_control.split(":", 1)[-1]
    return {
        "device_id": device_name,
        "domain": normalize_domain(device_name),
        "service": normalize_service(service_name),
        "arguments": {
            "day_of_week": dow,
            "hour_bucket": hour,
            "control_id": int(step[3]),
            "device_control": device_control,
        },
    }


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("smartsense")
    repo_roots = sorted(path for path in raw_dir.rglob("*") if path.is_dir() and (path / "data.zip").exists())
    if not repo_roots:
        raise FileNotFoundError("No SmartSense repo snapshot with data.zip found under data_raw/smartsense/")

    repo_root = repo_roots[0]
    archive_path = repo_root / "data.zip"
    if not archive_path.exists():
        archive_candidates = list(raw_dir.rglob("data.zip")) + list(raw_dir.glob("*.zip"))
        archive_path = archive_candidates[0] if archive_candidates else archive_path
    if not archive_path.exists():
        raise FileNotFoundError("SmartSense data.zip was not found.")

    processed_dir = processed_dataset_dir("smartsense")
    routine_rows: list[dict[str, Any]] = []
    log_rows: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    with zipfile.ZipFile(archive_path) as archive:
        region_roots = sorted({name.split("/", 1)[0] for name in archive.namelist() if "/" in name})
        for region in region_roots:
            dictionary_source = archive.read(f"{region}/dictionary.py").decode("utf-8")
            reverse_maps = {
                key: _reverse_mapping(value)
                for key, value in _exec_dictionary(dictionary_source).items()
            }

            routine_lines = archive.read(f"{region}/routine_device_corpus.txt").decode("utf-8").splitlines()
            for index, line in enumerate(routine_lines):
                device_ids = [int(token) for token in line.split() if token.strip()]
                if not device_ids:
                    continue
                actions = [
                    {
                        "device_id": reverse_maps["device_dict"].get(device_id, str(device_id)),
                        "domain": normalize_domain(reverse_maps["device_dict"].get(device_id, "")),
                        "service": "custom",
                        "arguments": {},
                    }
                    for device_id in device_ids
                ]
                task = build_task_t(
                    timestamp=None,
                    task_source="routine",
                    raw_text=f"SmartSense routine in region {region}",
                    parsed_slots={"sequence_device_ids": device_ids, "region": region},
                    trigger={"type": "habit", "detail": region},
                    target_devices_hint=[action["device_id"] for action in actions if action["device_id"]],
                    source_dataset=DATASET_NAME,
                    task_id=f"task-routine-{region}-{index}",
                )
                action_t = build_action_t(
                    task_id=task["task_id"],
                    timestamp=None,
                    actions=actions,
                    source_dataset=DATASET_NAME,
                    action_reason_type="routine",
                )
                routine_rows.append({"task_id": task["task_id"], "region": region, "device_sequence": actions})
                samples.append(
                    build_sample_t(
                        state=build_state_t(
                            home_id=f"smartsense_{region}",
                            timestamp=None,
                            sensor_events=[],
                            device_states={},
                            occupancy=None,
                            activity_hint="routine",
                            environment={"region": region},
                            source_dataset=DATASET_NAME,
                        ),
                        task=task,
                        target_action=action_t,
                        source_dataset=DATASET_NAME,
                        candidate_devices=task["target_devices_hint"],
                        weak_supervision=True,
                    )
                )

            train_array = np.array(__import__("pickle").loads(archive.read(f"{region}/trn_instance_10.pkl")))
            for index, sequence in enumerate(train_array):
                normalized_sequence = [_sequence_step_to_action(step.tolist(), reverse_maps) for step in sequence]
                if not normalized_sequence:
                    continue
                target = normalized_sequence[-1]
                history = normalized_sequence[:-1]
                task = build_task_t(
                    timestamp=None,
                    task_source="automation",
                    raw_text=f"Predict next SmartSense action in region {region}",
                    parsed_slots={"history_length": len(history), "region": region},
                    trigger={"type": "condition", "detail": "recent_history"},
                    target_devices_hint=[target["device_id"]] if target["device_id"] else [],
                    source_dataset=DATASET_NAME,
                    task_id=f"task-log-{region}-{index}",
                )
                action_t = build_action_t(
                    task_id=task["task_id"],
                    timestamp=None,
                    actions=[target],
                    source_dataset=DATASET_NAME,
                    action_reason_type="label",
                )
                log_rows.append(
                    {
                        "task_id": task["task_id"],
                        "region": region,
                        "history": history,
                        "target_action": target,
                    }
                )
                samples.append(
                    build_sample_t(
                        state=build_state_t(
                            home_id=f"smartsense_{region}",
                            timestamp=None,
                            sensor_events=[],
                            device_states={"recent_history": history},
                            occupancy=None,
                            activity_hint="next_action_prediction",
                            environment={"region": region},
                            source_dataset=DATASET_NAME,
                        ),
                        task=task,
                        target_action=action_t,
                        source_dataset=DATASET_NAME,
                        candidate_devices=[target["device_id"]] if target["device_id"] else [],
                        recent_history=history,
                        weak_supervision=False,
                    )
                )

    dataframe_to_parquet(pd.DataFrame(routine_rows), processed_dir / "routines.parquet")
    dataframe_to_parquet(pd.DataFrame(log_rows), processed_dir / "log_actions.parquet")
    dataframe_to_parquet(pd.DataFrame(samples).drop_duplicates(subset=["sample_id"]), processed_dir / "samples.parquet")
    log(f"Processed SmartSense dataset with {len(samples)} samples.")
