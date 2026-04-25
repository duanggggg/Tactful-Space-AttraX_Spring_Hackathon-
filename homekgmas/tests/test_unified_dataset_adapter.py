from app.datasets.source_registry import get_dataset_source_profile
from app.datasets.unified_adapter import build_unified_dataset_bundle


def test_dataset_source_profiles_separate_mode_without_changing_bundle_shape():
    fusion_profile = get_dataset_source_profile("smartsense")
    web_profile = get_dataset_source_profile("web_collected")

    assert fusion_profile.agent_mode == "fusion"
    assert web_profile.agent_mode == "web"
    assert fusion_profile.source_family != web_profile.source_family


def test_unified_dataset_bundle_builds_same_runtime_request_shape_for_fusion_and_web():
    common_kwargs = {
        "home_id": "home-1",
        "timestamp": "2026-04-22T20:00:00+08:00",
        "task_source": "user_nl",
        "raw_text": "Turn on the living room light",
        "actions": [
            {
                "device_id": "living_room_main",
                "domain": "light",
                "service": "turn_on",
                "arguments": {},
            }
        ],
        "parsed_slots": {"device": "light", "room": "living_room"},
        "trigger": {"type": "voice", "detail": "manual request"},
        "target_devices_hint": ["living_room_main"],
    }
    fusion_bundle = build_unified_dataset_bundle(source_dataset="home_assistant_datasets", **common_kwargs)
    web_bundle = build_unified_dataset_bundle(source_dataset="web_collected", **common_kwargs)

    fusion_request = fusion_bundle.to_task_request()
    web_request = web_bundle.to_task_request()

    assert set(fusion_request.model_dump().keys()) == set(web_request.model_dump().keys())
    assert fusion_request.description == web_request.description
    assert fusion_request.source == web_request.source
    assert set(fusion_request.preferences.keys()) == set(web_request.preferences.keys())
    assert fusion_request.preferences["parsed_slots"] == web_request.preferences["parsed_slots"]
    assert fusion_request.preferences["source_dataset"] != web_request.preferences["source_dataset"]
    assert fusion_request.preferences["agent_mode"] != web_request.preferences["agent_mode"]
