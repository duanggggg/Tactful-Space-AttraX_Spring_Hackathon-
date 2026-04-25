from pathlib import Path
import sys
from typing import Any

import json
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.datahub.normalize import normalize_domain, normalize_room, parse_timestamp
from app.datahub.io import dataframe_to_parquet
from app.datahub.schemas import build_action_t, build_sample_t, build_state_t, build_task_t
from scripts._data_common import (
    log,
    processed_dataset_dir,
    raw_dataset_dir,
    update_manifest,
)


DATASET_NAME = "home_assistant_datasets"


class HomeAssistantLoader(yaml.SafeLoader):
    """YAML loader that tolerates custom Home Assistant tags."""


def _construct_any(loader: HomeAssistantLoader, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


HomeAssistantLoader.add_constructor(None, _construct_any)
HomeAssistantLoader.add_multi_constructor("", lambda loader, tag_suffix, node: _construct_any(loader, node))


def _load_yaml(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    if "\n---" in text:
        documents = [doc for doc in yaml.load_all(text, Loader=HomeAssistantLoader) if doc is not None]
        if len(documents) == 1:
            return documents[0]
        return documents
    return yaml.load(text, Loader=HomeAssistantLoader)


def _service_from_state_change(domain: str, state: Any, attributes: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    service = "custom"
    arguments: dict[str, Any] = {}
    normalized_state = str(state).strip().lower()
    if normalized_state in {"on", "playing", "heat", "cool"}:
        service = "turn_on" if normalized_state in {"on", "playing"} else "custom"
    elif normalized_state in {"off", "idle"}:
        service = "turn_off"
    elif normalized_state == "locked":
        service = "lock"
    elif normalized_state == "unlocked":
        service = "unlock"
    elif normalized_state == "open":
        service = "open"
    elif normalized_state == "closed":
        service = "close"

    if "brightness" in attributes:
        service = "set_brightness"
        arguments["brightness"] = attributes["brightness"]
    if "temperature" in attributes:
        service = "set_temperature"
        arguments["temperature"] = attributes["temperature"]
    if "volume_level" in attributes:
        arguments["volume_level"] = attributes["volume_level"]
    if "percentage" in attributes:
        arguments["percentage"] = attributes["percentage"]
    if not arguments and state is not None:
        arguments["state"] = state
    return service, arguments


def _expect_changes_to_actions(expect_changes: dict[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for entity_id, change in (expect_changes or {}).items():
        if not isinstance(change, dict):
            continue
        domain = normalize_domain(entity_id.split(".", 1)[0] if "." in entity_id else entity_id)
        service, arguments = _service_from_state_change(
            domain,
            change.get("state"),
            change.get("attributes") or {},
        )
        actions.append(
            {
                "device_id": entity_id,
                "domain": domain,
                "service": service,
                "arguments": arguments,
            }
        )
    return actions


def _flatten_devices_yaml(path: Path) -> list[dict[str, Any]]:
    payload = _load_yaml(path)
    if not isinstance(payload, dict):
        return []
    rows: list[dict[str, Any]] = []
    home_id = path.stem
    for area_name, devices in (payload.get("devices") or {}).items():
        for device in devices or []:
            if not isinstance(device, dict):
                continue
            entity_name = str(device.get("name") or "").strip()
            domain = normalize_domain(device.get("device_type"))
            entity_id = f"{domain}.{entity_name.lower().replace(' ', '_')}" if entity_name else ""
            rows.append(
                {
                    "home_id": home_id,
                    "entity_id": entity_id,
                    "domain": domain,
                    "room": normalize_room(area_name),
                    "friendly_name": entity_name,
                    "source_file": str(path),
                }
            )
    return rows


def _fixtures_index(fixtures_path: Path) -> tuple[dict[str, str], list[dict[str, Any]]]:
    if not fixtures_path.exists():
        return {}, []
    payload = _load_yaml(fixtures_path) or {}
    area_lookup = {
        str(item.get("id")): normalize_room(item.get("name"))
        for item in payload.get("areas", [])
        if isinstance(item, dict)
    }
    entities = payload.get("entities", []) if isinstance(payload, dict) else []
    return area_lookup, entities if isinstance(entities, list) else []


def _build_assist_samples(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    tasks: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for assist_root in [repo_root / "datasets" / "assist", repo_root / "datasets" / "assist-mini"]:
        if not assist_root.exists():
            continue
        for yaml_path in sorted(assist_root.rglob("*.yaml")):
            if yaml_path.name.startswith("_") or yaml_path.name == "dataset_card.yaml":
                continue
            payload = _load_yaml(yaml_path)
            if not isinstance(payload, dict) or "tests" not in payload:
                continue
            area_lookup, entities = _fixtures_index(yaml_path.parent / "_fixtures.yaml")
            for test_index, test in enumerate(payload.get("tests", [])):
                if not isinstance(test, dict):
                    continue
                expect_changes = test.get("expect_changes") or {}
                action_rows = _expect_changes_to_actions(expect_changes)
                setup = test.get("setup") or {}
                state = build_state_t(
                    home_id=yaml_path.parent.name,
                    timestamp=None,
                    sensor_events=[],
                    device_states=setup,
                    occupancy=None,
                    activity_hint=payload.get("category"),
                    environment={"source_file": str(yaml_path.relative_to(repo_root))},
                    source_dataset=DATASET_NAME,
                )
                for sentence_index, sentence in enumerate(test.get("sentences", []) or []):
                    task = build_task_t(
                        timestamp=None,
                        task_source="user_nl",
                        raw_text=str(sentence),
                        parsed_slots={
                            "category": payload.get("category"),
                            "context_device": test.get("context_device"),
                        },
                        trigger={"type": "voice", "detail": None},
                        target_devices_hint=[row["device_id"] for row in action_rows if row.get("device_id")],
                        source_dataset=DATASET_NAME,
                        task_id=f"task-{yaml_path.stem}-{test_index}-{sentence_index}",
                    )
                    action_t = build_action_t(
                        task_id=task["task_id"],
                        timestamp=None,
                        actions=action_rows,
                        source_dataset=DATASET_NAME,
                        action_reason_type="expected_change",
                    )
                    sample = build_sample_t(
                        state=state,
                        task=task,
                        target_action=action_t,
                        candidate_devices=task["target_devices_hint"],
                        source_dataset=DATASET_NAME,
                        weak_supervision=not bool(action_rows),
                        split_key=yaml_path.parent.name,
                    )
                    tasks.append(task)
                    actions.append(action_t)
                    samples.append(sample)
    return tasks, actions, samples


def _build_automation_samples(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    tasks: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    automation_root = repo_root / "datasets" / "automations"
    if not automation_root.exists():
        return tasks, actions, samples

    for folder in sorted(path for path in automation_root.iterdir() if path.is_dir()):
        description_path = folder / "DESCRIPTION.md"
        solution_path = folder / "solution.yaml"
        if not solution_path.exists():
            continue
        description = description_path.read_text(encoding="utf-8").strip() if description_path.exists() else folder.name
        solution = _load_yaml(solution_path) or {}
        action_rows: list[dict[str, Any]] = []
        for item in solution.get("actions", []):
            if not isinstance(item, dict):
                continue
            for then_item in item.get("then", []):
                if not isinstance(then_item, dict):
                    continue
                service_name = str(then_item.get("service") or "").strip()
                entity_id = str((then_item.get("target") or {}).get("entity_id") or "").strip()
                domain = normalize_domain(entity_id.split(".", 1)[0] if "." in entity_id else service_name.split(".", 1)[0])
                service = service_name.split(".", 1)[-1] if "." in service_name else service_name
                action_rows.append(
                    {
                        "device_id": entity_id or domain,
                        "domain": domain,
                        "service": service,
                        "arguments": then_item.get("data") or {},
                    }
                )
        task = build_task_t(
            timestamp=None,
            task_source="automation",
            raw_text=description,
            parsed_slots={"automation_name": folder.name},
            trigger={"type": "condition", "detail": solution.get("triggers")},
            target_devices_hint=[row["device_id"] for row in action_rows if row.get("device_id")],
            source_dataset=DATASET_NAME,
            task_id=f"task-automation-{folder.name}",
        )
        action_t = build_action_t(
            task_id=task["task_id"],
            timestamp=None,
            actions=action_rows,
            source_dataset=DATASET_NAME,
            action_reason_type="rule",
        )
        state = build_state_t(
            home_id=folder.name,
            timestamp=None,
            sensor_events=[],
            device_states={},
            occupancy=None,
            activity_hint="automation",
            environment={"source_file": str(folder.relative_to(repo_root))},
            source_dataset=DATASET_NAME,
        )
        tasks.append(task)
        actions.append(action_t)
        samples.append(
            build_sample_t(
                state=state,
                task=task,
                target_action=action_t,
                candidate_devices=task["target_devices_hint"],
                source_dataset=DATASET_NAME,
                weak_supervision=not bool(action_rows),
                split_key=folder.name,
            )
        )
    return tasks, actions, samples


def _build_device_action_samples(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    tasks: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    conversation_path = repo_root / "datasets" / "device-actions-v2-collect" / "assist-llm-function-calling" / "train" / "conversation.jsonl"
    if not conversation_path.exists():
        return tasks, actions, samples
    for line_index, line in enumerate(conversation_path.read_text(encoding="utf-8").splitlines()):
        if not line.strip():
            continue
        record = json.loads(line)
        action_rows: list[dict[str, Any]] = []
        for tool_call in record.get("tool_calls", []) or []:
            if not isinstance(tool_call, dict):
                continue
            name = str(tool_call.get("name") or "")
            arguments = tool_call.get("arguments") or "{}"
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {"raw": arguments}
            service_map = {
                "HassTurnOn": "turn_on",
                "HassTurnOff": "turn_off",
                "HassLightSet": "set_brightness",
                "HassSetPosition": "custom",
                "HassMediaPause": "pause",
                "HassMediaUnpause": "play",
                "HassSetVolume": "custom",
                "HassVacuumStart": "start",
                "HassVacuumReturnToBase": "custom",
            }
            device_name = str(arguments.get("name") or arguments.get("area") or "")
            domain = normalize_domain(
                (arguments.get("domain") or ["other"])[0]
                if isinstance(arguments.get("domain"), list)
                else arguments.get("domain") or "other"
            )
            action_rows.append(
                {
                    "device_id": device_name,
                    "domain": domain,
                    "service": service_map.get(name, "custom"),
                    "arguments": arguments,
                }
            )
        if not action_rows:
            continue
        task = build_task_t(
            timestamp=None,
            task_source="user_nl",
            raw_text=str(record.get("input") or "").strip(),
            parsed_slots={"assistant_output": record.get("output")},
            trigger={"type": "voice", "detail": None},
            target_devices_hint=[row["device_id"] for row in action_rows if row.get("device_id")],
            source_dataset=DATASET_NAME,
            task_id=f"task-device-action-{line_index}",
        )
        action_t = build_action_t(
            task_id=task["task_id"],
            timestamp=None,
            actions=action_rows,
            source_dataset=DATASET_NAME,
            action_reason_type="label",
        )
        state = build_state_t(
            home_id=f"device_actions_{line_index}",
            timestamp=None,
            sensor_events=[],
            device_states={"instructions": record.get("instructions")},
            occupancy=None,
            activity_hint="device_action_collect",
            environment={},
            source_dataset=DATASET_NAME,
        )
        tasks.append(task)
        actions.append(action_t)
        samples.append(
            build_sample_t(
                state=state,
                task=task,
                target_action=action_t,
                candidate_devices=task["target_devices_hint"],
                source_dataset=DATASET_NAME,
                weak_supervision=False,
                split_key=str(line_index),
            )
        )
    return tasks, actions, samples


if __name__ == "__main__":
    raw_dir = raw_dataset_dir("home_assistant")
    repo_roots = sorted(path.parent for path in raw_dir.rglob("datasets") if path.is_dir())
    if not repo_roots:
        raise FileNotFoundError("No Home Assistant dataset repo snapshot found under data_raw/home_assistant/")

    processed_dir = processed_dataset_dir("home_assistant")
    entities: list[dict[str, Any]] = []
    tasks: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []

    for repo_root in repo_roots:
        for devices_dir in [repo_root / "datasets" / "devices-v3", repo_root / "datasets" / "devices-v2", repo_root / "datasets" / "devices"]:
            if not devices_dir.exists():
                continue
            for yaml_path in devices_dir.glob("*.yaml"):
                entities.extend(_flatten_devices_yaml(yaml_path))

        assist_tasks, assist_actions, assist_samples = _build_assist_samples(repo_root)
        auto_tasks, auto_actions, auto_samples = _build_automation_samples(repo_root)
        collect_tasks, collect_actions, collect_samples = _build_device_action_samples(repo_root)
        tasks.extend(assist_tasks + auto_tasks + collect_tasks)
        actions.extend(assist_actions + auto_actions + collect_actions)
        samples.extend(assist_samples + auto_samples + collect_samples)

    dataframe_to_parquet(pd.DataFrame(entities).drop_duplicates(), processed_dir / "entities.parquet")
    dataframe_to_parquet(pd.DataFrame(tasks).drop_duplicates(subset=["task_id"]), processed_dir / "tasks.parquet")
    dataframe_to_parquet(pd.DataFrame(actions).drop_duplicates(subset=["task_id"]), processed_dir / "actions.parquet")
    dataframe_to_parquet(pd.DataFrame(samples).drop_duplicates(subset=["sample_id"]), processed_dir / "samples.parquet")

    update_manifest(
        dataset_name=DATASET_NAME,
        source_url="https://github.com/allenporter/home-assistant-datasets",
        local_path=str(raw_dir),
        license_if_known="Apache-2.0",
        download_method="github_zip",
        status="success",
        notes=f"Processed {len(samples)} Home Assistant samples.",
    )
    log(f"Processed Home Assistant dataset with {len(samples)} samples.")
