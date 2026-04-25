from fastapi.testclient import TestClient

from tests.conftest import build_test_app


def test_demo_task_route_runs_end_to_end(tmp_path):
    app, settings = build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        f"{settings.api_prefix}/tasks/demo",
        json={"description": "Create a cool calm evening with soft light and music"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "accepted"
    assert payload["user_view"]["summary"]
    assert "cooling_agent" in payload["selected_agents"]
    assert payload["execution"]["success"] is True
    assert payload["agent_dialogue"]
    assert any(line["agent_name"] == "cooling_agent" for line in payload["agent_dialogue"])
    assert any(line["agent_name"] == "lighting_agent" for line in payload["agent_dialogue"])
    assert any(line["agent_name"] == "music_agent" for line in payload["agent_dialogue"])
    assert payload["compression"]["accepted_decisions"]
    assert payload["plan"]["rationale"]
    assert payload["plan"]["decision_confidence"] > 0
    assert payload["plan"]["policy_checks_passed"]


def test_root_route_returns_service_navigation(tmp_path):
    app, settings = build_test_app(tmp_path)
    client = TestClient(app)

    response = client.get("/")

    assert response.status_code == 200
    payload = response.json()
    assert payload["project"] == settings.project_name
    assert payload["routes"]["docs"] == "/docs"
    assert payload["routes"]["demo_task"] == f"{settings.api_prefix}/tasks/demo"


def test_demo_task_get_route_returns_usage(tmp_path):
    app, settings = build_test_app(tmp_path)
    client = TestClient(app)

    response = client.get(f"{settings.api_prefix}/tasks/demo")

    assert response.status_code == 200
    payload = response.json()
    assert payload["method"] == "POST"
    assert payload["path"] == f"{settings.api_prefix}/tasks/demo"


def test_frontend_request_returns_clean_dialogue_and_execution_mapping(tmp_path):
    app, settings = build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        f"{settings.api_prefix}/tasks/demo",
        json={"description": "Create a cool calm evening with soft light and music"},
    )

    assert response.status_code == 200
    payload = response.json()

    dialogue_by_agent = {}
    for line in payload["agent_dialogue"]:
        dialogue_by_agent.setdefault(line["agent_name"], []).append(line)

    assert set(payload["selected_agents"]).issubset(dialogue_by_agent.keys())
    assert all(isinstance(line["rationale"], list) for line in payload["agent_dialogue"])
    assert all("utterance" not in line for line in payload["agent_dialogue"])
    assert any(line["actions"] for line in dialogue_by_agent["cooling_agent"])
    assert any(line["actions"] for line in dialogue_by_agent["lighting_agent"])
    assert any(line["actions"] for line in dialogue_by_agent["music_agent"])

    selected_ids = {action["action_id"] for action in payload["plan"]["selected_actions"]}
    applied_ids = {action["action_id"] for action in payload["execution"]["applied_actions"]}
    assert selected_ids == applied_ids
    assert all(action["status"] == "applied" for action in payload["execution"]["applied_actions"])


def test_quiet_hours_triggers_revision_and_removes_music(tmp_path):
    app, settings = build_test_app(tmp_path)
    environment = app.state.central_node.simulator.backend.environment
    environment._current_time = environment._current_time.replace(hour=23, minute=30)
    environment._refresh_derived_state()
    client = TestClient(app)

    response = client.post(
        f"{settings.api_prefix}/tasks/demo",
        json={"description": "Play calm music for the living room tonight"},
    )

    assert response.status_code == 200
    payload = response.json()
    selected = payload["plan"]["selected_actions"]
    assert all(action["device_id"] != "music_player" for action in selected)
    assert any("quiet-hours" in conflict for conflict in payload["conflicts"])
    assert any(line["agent_name"] == "music_agent" for line in payload["agent_dialogue"])
    assert payload["user_view"]["scene_label"] == "Night mode"


def test_explicit_volume_task_prefers_media_agent_scope(tmp_path):
    app, settings = build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        f"{settings.api_prefix}/tasks/demo",
        json={"description": "Turn the volume down to 50%"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_agents"] == ["music_agent"]
    assert any(action["device_id"] == "music_player" and action["attribute"] == "volume" for action in payload["plan"]["selected_actions"])
    assert all(action["device_id"] == "music_player" for action in payload["plan"]["selected_actions"])


def test_structured_humidity_task_selects_switch_agent(tmp_path):
    app, settings = build_test_app(tmp_path)
    client = TestClient(app)

    response = client.post(
        f"{settings.api_prefix}/tasks/demo",
        json={
            "description": "请把空气净化器湿度调低到30",
            "preferences": {
                "parsed_slots": {
                    "attribute": "humidity",
                    "value": "30",
                    "room": "客厅",
                },
                "source_dataset": "zh_commands",
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_agents"] == ["switch_agent"]
    assert any(action["attribute"] == "humidity" for action in payload["plan"]["selected_actions"])


def test_scheduled_task_routes_store_and_list_tasks(tmp_path):
    app, settings = build_test_app(tmp_path)
    client = TestClient(app)

    create_response = client.post(
        f"{settings.api_prefix}/tasks/scheduled",
        json={
            "task_id": "task-scheduled-1",
            "description": "Dim the lights before bedtime",
            "source": "scheduled",
            "run_at": "2026-04-06T21:30:00Z",
            "constraints": {"mode": "bedtime"},
        },
    )
    assert create_response.status_code == 200

    list_response = client.get(f"{settings.api_prefix}/tasks/scheduled")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert len(payload) == 1
    assert payload[0]["task_id"] == "task-scheduled-1"
    assert payload[0]["status"] == "pending"


def test_run_due_scheduled_tasks_executes_and_marks_completed(tmp_path):
    app, settings = build_test_app(tmp_path)
    client = TestClient(app)

    client.post(
        f"{settings.api_prefix}/tasks/scheduled",
        json={
            "task_id": "task-due-1",
            "description": "Create a cool calm evening with soft light and music",
            "source": "scheduled",
            "run_at": "2026-04-05T10:00:00Z",
        },
    )
    client.post(
        f"{settings.api_prefix}/tasks/scheduled",
        json={
            "task_id": "task-future-1",
            "description": "Prepare the lights later",
            "source": "scheduled",
            "run_at": "2026-04-07T10:00:00Z",
        },
    )

    run_response = client.post(
        f"{settings.api_prefix}/tasks/scheduled/run-due",
        params={"triggered_at": "2026-04-06T12:00:00Z"},
    )

    assert run_response.status_code == 200
    payload = run_response.json()
    assert payload["executed_count"] == 1
    assert payload["executed_task_ids"] == ["task-due-1"]
    assert payload["skipped_task_ids"] == ["task-future-1"]
    assert payload["results"][0]["task_id"] == "task-due-1"

    list_response = client.get(f"{settings.api_prefix}/tasks/scheduled")
    statuses = {task["task_id"]: task["status"] for task in list_response.json()}
    assert statuses["task-due-1"] == "completed"
    assert statuses["task-future-1"] == "pending"
