from fastapi.testclient import TestClient

from app.environment.dynamic_environment import DynamicHomeEnvironment
from app.environment.sensor_hub import SensorHub
from app.environment.service_app import create_simulator_app
from app.environment.simulator import EmbeddedSimulatorBackend, HomeSimulator
from app.environment.web_environment import WebHomeEnvironment
from app.planning.action import PlannedAction
from app.planning.plan import ExecutionPlan


def test_simulator_applies_actions():
    environment = DynamicHomeEnvironment(sensors=SensorHub().get_snapshot())
    simulator = HomeSimulator(backend=EmbeddedSimulatorBackend(environment))
    plan = ExecutionPlan(
        task_id="task-sim",
        selected_actions=[
            PlannedAction(
                device_id="living_room_main",
                attribute="power",
                value=True,
                reason="Need light",
                requested_by="lighting_agent",
            )
        ],
    )

    result = simulator.execute(plan)

    assert result.success is True
    assert result.applied_actions[0].action_id == plan.selected_actions[0].action_id
    assert result.applied_actions[0].status == "applied"
    assert result.state_snapshot["devices"]["lights"]["living_room_main"]["power"] is True


def test_dynamic_environment_changes_outdoor_and_sensor_values():
    environment = DynamicHomeEnvironment(sensors=SensorHub().get_snapshot())

    initial_state = environment.get_home_state()
    updated_state = environment.tick(minutes=45)

    assert updated_state.outdoor.outdoor_temperature_c != initial_state.outdoor.outdoor_temperature_c
    assert updated_state.sensors.current_time != initial_state.sensors.current_time
    assert updated_state.sensors.ambient_light_level != initial_state.sensors.ambient_light_level


def test_simulator_service_exposes_state_and_dashboard():
    client = TestClient(create_simulator_app())

    html_response = client.get("/")
    state_response = client.get("/api/state")

    assert html_response.status_code == 200
    assert "Dynamic Home Simulator" in html_response.text
    assert state_response.status_code == 200
    payload = state_response.json()
    assert "outdoor" in payload
    assert "sensors" in payload
    assert "devices" in payload


def test_web_environment_action_updates_agent_state_and_indoor_metrics():
    environment = WebHomeEnvironment()

    initial = environment.snapshot_payload()
    updated = environment.apply_action("air_conditioner.living.cool_24")

    assert updated["agents"]["air_conditioner"]["living"]["power"] is True
    assert updated["agents"]["air_conditioner"]["living"]["mode"] == "cool"
    assert updated["agents"]["air_conditioner"]["living"]["target_temp"] == 24
    assert updated["indoor"]["living"]["temp"] < initial["indoor"]["living"]["temp"]
    assert updated["indoor"]["living"]["energy"] > initial["indoor"]["living"]["energy"]


def test_web_simulator_service_exposes_dashboard_catalog_and_action_loop():
    client = TestClient(create_simulator_app())

    html_response = client.get("/web")
    catalog_response = client.get("/api/web/actions")
    state_response = client.get("/api/web/state")
    action_response = client.post("/api/web/actions", json={"action_key": "lighting.living.focus"})

    assert html_response.status_code == 200
    assert "Web Agent Simulator" in html_response.text
    assert catalog_response.status_code == 200
    catalog = catalog_response.json()
    assert any(item["action_key"] == "lighting.living.focus" for item in catalog)
    assert state_response.status_code == 200
    state_payload = state_response.json()
    assert "meta" in state_payload
    assert "outdoor" in state_payload
    assert "indoor" in state_payload
    assert "agents" in state_payload
    assert action_response.status_code == 200
    updated_payload = action_response.json()
    assert updated_payload["agents"]["lighting"]["living"]["power"] is True
