from fastapi.testclient import TestClient

from app.datasets.question_builder import ContextQuestionBuilder
from app.environment.home_state import DeviceState, HomeState
from tests.conftest import build_test_app


def test_context_question_builder_generates_distinct_questions():
    state = HomeState(
        sensors={
            "room_temperature_c": 28.2,
            "bedroom_temperature_c": 25.6,
            "room_humidity_pct": 67,
            "ambient_light_level": 18,
            "occupancy": {"living_room": True, "bedroom": False},
            "current_time": "2026-04-10T22:30:00+08:00",
            "time_of_day": "night",
            "quiet_hours": True,
        },
        devices=DeviceState(),
        outdoor={
            "weather": "rainy",
            "outdoor_temperature_c": 24.0,
            "outdoor_light_level": 8,
            "humidity_pct": 88,
            "wind_speed_mps": 3.1,
            "cloud_cover_pct": 78,
        },
    )
    questions = ContextQuestionBuilder().build_tasks_from_state(state, count=6)
    descriptions = [task.description for task in questions]

    assert len(descriptions) >= 4
    assert len(set(descriptions)) == len(descriptions)
    assert any("late night" in description.lower() or "night" in description.lower() for description in descriptions)


def test_current_context_route_returns_home_state(tmp_path):
    app, settings = build_test_app(tmp_path)
    client = TestClient(app)

    response = client.get(f"{settings.api_prefix}/tasks/context/current")

    assert response.status_code == 200
    payload = response.json()
    assert "sensors" in payload
    assert "devices" in payload
    assert "outdoor" in payload
