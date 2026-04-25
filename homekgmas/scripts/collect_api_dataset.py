from pathlib import Path
import sys
import json
from datetime import datetime, timezone

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx

from app.api.schemas import TaskRequest
from app.core.config import build_settings
from app.datasets.question_builder import ContextQuestionBuilder
from app.environment.home_state import HomeState
from app.storage.file_store import FileStore


TARGET_SAMPLE_COUNT = 8
LOCAL_API_BASE = "http://127.0.0.1:8000"


def build_dataset_record(task: TaskRequest, response_payload: dict, context_payload: dict) -> dict:
    plan = response_payload.get("plan", {})
    execution = response_payload.get("execution", {})
    return {
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "question": task.description,
        "task": task.model_dump(mode="json"),
        "context_before": context_payload,
        "user_view": response_payload.get("user_view", {}),
        "selected_agents": response_payload.get("selected_agents", []),
        "conflicts": response_payload.get("conflicts", []),
        "plan_summary": {
            "selected_actions": plan.get("selected_actions", []),
            "rejected_actions": plan.get("rejected_actions", []),
            "rationale": plan.get("rationale", []),
            "decision_confidence": plan.get("decision_confidence"),
            "consensus_level": plan.get("consensus_level"),
            "policy_checks_passed": plan.get("policy_checks_passed", []),
        },
        "execution_summary": {
            "success": execution.get("success"),
            "applied_actions": execution.get("applied_actions", []),
            "notes": execution.get("notes", []),
        },
        "debug_view": {
            "agent_dialogue": response_payload.get("agent_dialogue", []),
            "compression": response_payload.get("compression", {}),
            "memory_record_id": response_payload.get("memory_record_id"),
            "created_at": response_payload.get("created_at"),
        },
    }


def _question_key(text: str) -> str:
    return " ".join("".join(char if char.isalnum() else " " for char in text.lower()).split())


def build_local_client(base_url: str) -> httpx.Client:
    """Create an HTTP client for local services without inheriting proxy settings."""

    return httpx.Client(
        base_url=base_url,
        timeout=httpx.Timeout(connect=5.0, read=60.0, write=20.0, pool=20.0),
        trust_env=False,
    )


if __name__ == "__main__":
    settings = build_settings()
    file_store = FileStore()
    question_builder = ContextQuestionBuilder()
    dataset_dir = settings.output_dir / "datasets"
    file_store.ensure_dir(dataset_dir)
    dataset_path = dataset_dir / "api_task_runs.jsonl"
    tasks_path = dataset_dir / "api_task_inputs.jsonl"

    existing_questions = {
        _question_key(payload.get("description", ""))
        for payload in file_store.read_jsonl(tasks_path)
        if isinstance(payload, dict)
    }
    existing_questions |= {
        _question_key(payload.get("question", ""))
        for payload in file_store.read_jsonl(dataset_path)
        if isinstance(payload, dict)
    }

    api_client = build_local_client(LOCAL_API_BASE)
    simulator_client = build_local_client(settings.simulator_api_base)
    written = 0

    while written < TARGET_SAMPLE_COUNT:
        try:
            context_response = simulator_client.get("/api/state")
        except httpx.HTTPError as exc:
            raise SystemExit(
                f"Failed to read simulator context from {settings.simulator_api_base}/api/state. "
                "Make sure the simulator server is running on port 8011. "
                f"Original error: {exc}"
            ) from exc
        context_response.raise_for_status()
        context_payload = context_response.json()
        state = HomeState(**context_payload)

        candidates = question_builder.build_tasks_from_state(
            state,
            count=3,
            existing_texts=existing_questions,
        )
        if not candidates:
            break

        task = candidates[0]
        existing_questions.add(_question_key(task.description))
        file_store.append_jsonl(
            tasks_path,
            {
                **task.model_dump(mode="json"),
                "generated_from_context_time": state.sensors.current_time,
                "time_of_day": state.sensors.time_of_day,
                "weather": state.outdoor.weather,
                "context_source": f"{settings.simulator_api_base}/api/state",
            },
        )

        try:
            response = api_client.post("/api/v1/tasks/demo", json=task.model_dump(mode="json"))
        except httpx.HTTPError as exc:
            raise SystemExit(
                "Failed to execute the generated question on the main API at "
                f"{LOCAL_API_BASE}/api/v1/tasks/demo. "
                "Make sure the main server is running on port 8000, and preferably start it with "
                "`HOMEKG_LLM_ENABLED=false` to avoid slow external model calls during dataset collection. "
                f"Original error: {exc}"
            ) from exc
        response.raise_for_status()
        payload = response.json()
        file_store.append_jsonl(dataset_path, build_dataset_record(task, payload, context_payload))
        written += 1

    print(
        json.dumps(
            {
                "dataset_path": str(dataset_path),
                "task_source_path": str(tasks_path),
                "records_written": written,
                "target_sample_count": TARGET_SAMPLE_COUNT,
                "context_source": f"{settings.simulator_api_base}/api/state",
                "task_execution_endpoint": f"{LOCAL_API_BASE}/api/v1/tasks/demo",
            },
            indent=2,
            ensure_ascii=True,
        )
    )
