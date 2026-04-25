from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import shutil
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

try:
    import pandas as pd
except Exception:
    pd = None

from app.agents.agent_registry import AgentRegistry
from app.api.schemas import TaskRequest
from app.core.config import build_settings
from app.datasets.loaders.task_builder import build_synthetic_tasks
from app.environment.simulator import HomeSimulator
from app.llm.client import OpenAIChatCompletionsClient
from app.memory.coordinator import MemoryCoordinator
from app.memory.graph_retriever import GraphRetriever
from app.memory.triple_store import TripleStore
from app.memory.workspace_store import WorkspaceMemoryStore
from app.orchestrator.central_node import CentralNode
from app.storage.file_store import FileStore


def build_central_node():
    runtime_root = PROJECT_ROOT / "outputs" / "synthetic_runtime"
    if runtime_root.exists():
        shutil.rmtree(runtime_root)
    settings = build_settings(
        {
            "llm_enabled": False,
            "openai_api_key": None,
            "openai_api_base": None,
            "openai_model": None,
            "simulator_mode": "embedded",
            "output_dir": PROJECT_ROOT / "outputs",
            "memory_dir": runtime_root / "memory",
            "agent_workspace_dir": runtime_root / "agent_workspaces" / "fusion",
            "log_dir": runtime_root / "logs",
            "report_dir": runtime_root / "reports",
        }
    )
    llm_client = None
    triple_store = TripleStore(settings.memory_dir)
    workspace_store = WorkspaceMemoryStore(settings.agent_workspace_dir)
    simulator = HomeSimulator.from_settings(settings)
    registry = AgentRegistry.from_config(
        settings.agents_config_path,
        workspace_store=workspace_store,
        llm_client=llm_client,
        agent_mode=settings.agent_mode,
        agent_catalog_path=settings.agent_catalog_path,
    )
    retriever = GraphRetriever(triple_store)
    memory_coordinator = MemoryCoordinator(
        graph_retriever=retriever,
        workspace_store=workspace_store,
        primary_backend=settings.primary_memory_backend,
    )
    central_node = CentralNode.build_default(
        simulator=simulator,
        agent_registry=registry,
        triple_store=triple_store,
        memory_coordinator=memory_coordinator,
        compression_window=settings.compression_window,
    )
    return settings, simulator, triple_store, central_node


def ensure_stage_dirs(run_root: Path, file_store: FileStore) -> dict[str, Path]:
    stage_dirs = {
        "manifest": run_root / "00_manifest",
        "tasks": run_root / "01_tasks",
        "states": run_root / "02_states",
        "agents": run_root / "03_selected_agents",
        "dialogue": run_root / "04_dialogue",
        "plans": run_root / "05_plans",
        "execution": run_root / "06_execution",
        "memory": run_root / "07_memory",
        "episodes": run_root / "08_episodes",
        "knowledge": run_root / "09_knowledge",
    }
    for path in stage_dirs.values():
        file_store.ensure_dir(path)
    return stage_dirs


def action_to_service(action: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    attribute = action.get("attribute")
    value = action.get("value")
    if attribute == "power":
        return ("turn_on", {}) if bool(value) else ("turn_off", {})
    if attribute == "brightness":
        return "set_brightness", {"brightness": value}
    if attribute == "target_temperature":
        return "set_temperature", {"temperature_c": value}
    if attribute == "playlist":
        return "play", {"playlist": value}
    if attribute == "volume":
        return "set_volume", {"volume": value}
    if attribute == "speed":
        return "set_speed", {"speed": value}
    if attribute == "oscillate":
        return "set_oscillation", {"oscillate": value}
    if attribute == "position":
        if str(value).lower() == "open":
            return "open", {}
        if str(value).lower() == "closed":
            return "close", {}
        return "custom", {"position": value}
    if attribute == "locked":
        return ("lock", {}) if bool(value) else ("unlock", {})
    if attribute == "status":
        if str(value).lower() == "cleaning":
            return "start", {"status": value}
        if str(value).lower() in {"idle", "docked"}:
            return "stop", {"status": value}
        return "custom", {"status": value}
    if attribute == "mode":
        return "custom", {"mode": value}
    return "custom", {attribute: value}



def infer_domain(device_id: str) -> str:
    if device_id.startswith("living_room_ac") or device_id.startswith("bedroom_ac"):
        return "climate"
    if device_id in {"living_room_main", "bedroom_lamp"} or "light" in device_id or "lamp" in device_id:
        return "light"
    if device_id == "music_player":
        return "media_player"
    if "fan" in device_id:
        return "fan"
    if "curtain" in device_id or "blind" in device_id:
        return "cover"
    if "lock" in device_id:
        return "lock"
    if device_id in {"air_purifier", "bedroom_humidifier"}:
        return "switch"
    if "vacuum" in device_id:
        return "appliance"
    return "other"



def build_episode_record(task: TaskRequest, result_payload: dict[str, Any], state_before: dict[str, Any]) -> dict[str, Any]:
    selected_actions = result_payload.get("plan", {}).get("selected_actions", [])
    candidate_devices = []
    seen_candidates: set[str] = set()
    synthetic_discussion = []
    for entry in result_payload.get("agent_dialogue", []):
        agent_name = entry.get("agent_name")
        for rank, action in enumerate(entry.get("actions", []), start=1):
            device_id = action.get("device_id")
            if device_id and device_id not in seen_candidates:
                seen_candidates.add(device_id)
                candidate_devices.append(
                    {
                        "device_id": device_id,
                        "domain": infer_domain(device_id),
                        "candidate_source": agent_name,
                        "candidate_rank": rank,
                    }
                )
        synthetic_discussion.append(
            {
                "agent_name": agent_name,
                "summary": entry.get("summary", ""),
                "rationale": entry.get("rationale", []),
                "concerns": entry.get("concerns", []),
                "actions": entry.get("actions", []),
                "is_synthetic": True,
            }
        )

    target_actions = []
    for index, action in enumerate(selected_actions, start=1):
        service, arguments = action_to_service(action)
        target_actions.append(
            {
                "sequence_index": index,
                "device_id": action.get("device_id"),
                "domain": infer_domain(action.get("device_id", "")),
                "service": service,
                "arguments": arguments,
                "attribute": action.get("attribute"),
                "value": action.get("value"),
                "requested_by": action.get("requested_by"),
                "reason": action.get("reason"),
            }
        )

    return {
        "sample_id": task.task_id,
        "task_id": task.task_id,
        "task_description": task.description,
        "task_source": task.source,
        "state_before": state_before,
        "selected_agents": result_payload.get("selected_agents", []),
        "candidate_devices": candidate_devices,
        "synthetic_discussion": synthetic_discussion,
        "plan": result_payload.get("plan", {}),
        "target_actions": target_actions,
        "execution": result_payload.get("execution", {}),
        "conflicts": result_payload.get("conflicts", []),
        "memory_record_id": result_payload.get("memory_record_id"),
        "created_at": result_payload.get("created_at"),
        "label_quality": "strong",
    }



def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True))
            handle.write("\n")



def main() -> None:
    sample_count = int(sys.argv[1]) if len(sys.argv) > 1 else 16
    settings, simulator, triple_store, central_node = build_central_node()
    file_store = FileStore()

    run_id = datetime.now(timezone.utc).strftime("run_%Y%m%dT%H%M%SZ")
    run_root = settings.output_dir / "datasets" / "synthetic_pipeline" / run_id
    stage_dirs = ensure_stage_dirs(run_root, file_store)

    simulator.reset()
    tasks = build_synthetic_tasks(sample_count=sample_count)
    file_store.write_json(
        stage_dirs["manifest"] / "run_manifest.json",
        {
            "run_id": run_id,
            "sample_count": sample_count,
            "llm_enabled": settings.llm_enabled,
            "simulator_mode": settings.simulator_mode,
            "memory_backend": settings.primary_memory_backend,
            "agents_config_path": str(settings.agents_config_path),
            "devices_config_path": str(settings.devices_config_path),
        },
    )

    task_rows: list[dict[str, Any]] = []
    state_rows: list[dict[str, Any]] = []
    selected_agent_rows: list[dict[str, Any]] = []
    dialogue_rows: list[dict[str, Any]] = []
    plan_rows: list[dict[str, Any]] = []
    execution_rows: list[dict[str, Any]] = []
    memory_rows: list[dict[str, Any]] = []
    knowledge_rows: list[dict[str, Any]] = []
    episode_rows: list[dict[str, Any]] = []

    agent_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()

    for index, task in enumerate(tasks, start=1):
        print(f"[synthetic-pipeline] running task {index}/{len(tasks)}: {task.description}")
        state_before_model = simulator.get_home_state()
        state_before = state_before_model.model_dump(mode="json")
        result = central_node.handle_task(task)
        result_payload = result.model_dump(mode="json")
        memory_record_path = triple_store.records_dir / f"{result.memory_record_id}.json"
        memory_payload = file_store.read_json(memory_record_path, default={})
        episode = build_episode_record(task, result_payload, state_before)

        task_rows.append(task.model_dump(mode="json"))
        state_rows.append({
            "task_id": task.task_id,
            "captured_at": result_payload.get("created_at"),
            "state_before": state_before,
        })
        selected_agent_rows.append(
            {
                "task_id": task.task_id,
                "selected_agents": result_payload.get("selected_agents", []),
            }
        )
        dialogue_rows.append(
            {
                "task_id": task.task_id,
                "agent_dialogue": result_payload.get("agent_dialogue", []),
                "compression": result_payload.get("compression", {}),
            }
        )
        plan_rows.append(
            {
                "task_id": task.task_id,
                "plan": result_payload.get("plan", {}),
                "user_view": result_payload.get("user_view", {}),
                "conflicts": result_payload.get("conflicts", []),
            }
        )
        execution_rows.append(
            {
                "task_id": task.task_id,
                "execution": result_payload.get("execution", {}),
            }
        )
        memory_rows.append(memory_payload)
        knowledge_rows.extend(memory_payload.get("triples", []))
        episode_rows.append(episode)

        for agent_name in result_payload.get("selected_agents", []):
            agent_counter[agent_name] += 1
        for action in episode["target_actions"]:
            action_counter[action["service"]] += 1

        file_store.write_json(stage_dirs["episodes"] / f"{task.task_id}.json", episode)

    write_jsonl(stage_dirs["tasks"] / "tasks.jsonl", task_rows)
    write_jsonl(stage_dirs["states"] / "states_before.jsonl", state_rows)
    write_jsonl(stage_dirs["agents"] / "selected_agents.jsonl", selected_agent_rows)
    write_jsonl(stage_dirs["dialogue"] / "dialogue.jsonl", dialogue_rows)
    write_jsonl(stage_dirs["plans"] / "plans.jsonl", plan_rows)
    write_jsonl(stage_dirs["execution"] / "executions.jsonl", execution_rows)
    write_jsonl(stage_dirs["memory"] / "memory_records.jsonl", memory_rows)
    write_jsonl(stage_dirs["knowledge"] / "triples.jsonl", knowledge_rows)
    write_jsonl(stage_dirs["episodes"] / "episodes.jsonl", episode_rows)
    file_store.write_json(stage_dirs["episodes"] / "episode_preview.json", episode_rows[:3])

    if pd is not None:
        parquet_rows = []
        for row in episode_rows:
            parquet_rows.append(
                {
                    key: json.dumps(value, ensure_ascii=True)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )
        pd.DataFrame(parquet_rows).to_parquet(stage_dirs["episodes"] / "episodes.parquet", index=False)

    summary = {
        "run_id": run_id,
        "run_root": str(run_root),
        "sample_count": len(episode_rows),
        "agents_used": dict(agent_counter),
        "services_selected": dict(action_counter),
        "memory_records_written": len(memory_rows),
        "knowledge_triples_written": len(knowledge_rows),
    }
    file_store.write_json(run_root / "summary.json", summary)

    print(json.dumps(summary, indent=2, ensure_ascii=True))
    print(f"[synthetic-pipeline] outputs written to {run_root}")


if __name__ == "__main__":
    main()
