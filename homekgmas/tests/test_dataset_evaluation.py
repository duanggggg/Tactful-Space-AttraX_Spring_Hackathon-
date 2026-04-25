from pathlib import Path
import json

from app.evaluation.dataset_runner import (
    build_dataset_eval_report,
    build_home_state_from_snapshot,
    build_task_request_from_rows,
    infer_service_from_target_action,
)
from app.evaluation.baselines import build_fusion_dataset_baseline_specs
from app.evaluation.fusion_baseline_runner import build_fusion_baseline_comparison_report


def test_build_home_state_from_snapshot_uses_timestamp_and_device_state():
    home_state = build_home_state_from_snapshot(
        {
            "snapshot_ts": "2026-04-10T22:30:00+08:00",
            "occupancy_status": "occupied",
            "sensor_summary_json": "{}",
            "device_state_json": '{"light.living_room_light": {"attributes": {"brightness": 80}, "state": "on"}}',
            "environment_json": '{"weather": "rainy", "temperature": 24.5}',
            "history_action_summary_json": "[]",
        }
    )

    assert home_state.sensors.time_of_day == "night"
    assert home_state.sensors.quiet_hours is True
    assert home_state.sensors.occupancy["living_room"] is True
    assert home_state.devices.lights["living_room_main"].power is True
    assert home_state.devices.lights["living_room_main"].brightness == 80
    assert home_state.outdoor.weather == "rainy"


def test_infer_service_from_target_action_recovers_turn_on_from_custom_state():
    service = infer_service_from_target_action(
        {
            "domain": "light",
            "service_name_norm": "custom",
            "arguments_json": {"state": "on"},
        }
    )

    assert service == "turn_on"


def test_infer_service_and_domain_fallback_use_device_domain():
    service = infer_service_from_target_action(
        {
            "device_domain": "media_player",
            "service_name_norm": "custom",
            "arguments_json": {"volume": 30},
        }
    )

    assert service == "custom"


def test_dataset_eval_report_runs_on_small_synthetic_row(tmp_path):
    row = {
        "sample_id": "sample-1",
        "state_id": "state-1",
        "task_id": "task-1",
        "target_actions_json": '[{"domain":"light","service_name_norm":"custom","arguments_json":{"state":"on"}}]',
        "label_quality": "strong",
        "split": "test",
        "task_source": "user_nl",
        "raw_text": "Please turn on the living room light",
        "parsed_slots_json": '{"device":"light"}',
        "trigger_json": '{"type":"voice"}',
        "source_dataset": "home_assistant_datasets",
        "snapshot_ts": "2026-04-10T20:00:00+08:00",
        "occupancy_status": "occupied",
        "sensor_summary_json": "{}",
        "device_state_json": '{"light.living_room_light": {"attributes": {"brightness": 0}, "state": "off"}}',
        "environment_json": "{}",
        "history_action_summary_json": "[]",
    }

    report = build_dataset_eval_report(
        rows=[row],
        output_dir=tmp_path / "eval_outputs",
        primary_memory_backend="none",
        llm_enabled=False,
    )

    assert report.summary.sample_count == 1
    assert report.records[0].source_dataset == "home_assistant_datasets"
    assert report.records[0].selected_agent_count >= 1
    assert report.records[0].final_domain_recall >= 1.0
    assert report.records[0].web_metrics is None
    assert report.web_summary is None


def test_dataset_eval_report_adds_web_only_metrics_for_web_sources(tmp_path):
    row = {
        "sample_id": "web-sample-1",
        "state_id": "state-1",
        "task_id": "task-1",
        "target_actions_json": '[{"domain":"light","service_name_norm":"set_brightness","arguments_json":{"brightness":72}}]',
        "label_quality": "strong",
        "split": "test",
        "task_source": "user_nl",
        "raw_text": "Please make the living room brighter for reading",
        "parsed_slots_json": '{"device":"light","room":"living_room","attribute":"brightness"}',
        "trigger_json": '{"type":"web"}',
        "source_dataset": "web_collected",
        "snapshot_ts": "2026-04-10T19:00:00+08:00",
        "occupancy_status": "occupied",
        "sensor_summary_json": "{}",
        "device_state_json": '{"light.living_room_light": {"attributes": {"brightness": 10}, "state": "off"}}',
        "environment_json": json.dumps(
            {
                "living_temp": 27.2,
                "bedroom_temp": 25.6,
                "living_humidity": 58,
                "bedroom_humidity": 55,
                "living_air": 61,
                "bedroom_air": 67,
                "living_brightness": 18,
                "bedroom_brightness": 14,
                "living_noise": 22,
                "bedroom_noise": 18,
                "living_energy": 8,
                "bedroom_energy": 5,
                "outdoor_temp": 29.0,
                "outdoor_humidity": 64,
                "outdoor_air": 72,
                "outdoor_noise": 28,
                "outdoor_brightness": 66,
            }
        ),
        "history_action_summary_json": "[]",
    }

    report = build_dataset_eval_report(
        rows=[row],
        output_dir=tmp_path / "eval_outputs",
        primary_memory_backend="none",
        llm_enabled=False,
    )

    assert report.summary.sample_count == 1
    assert report.records[0].source_dataset == "web_collected"
    assert report.records[0].web_metrics is not None
    assert report.records[0].web_metrics.evaluated is True
    assert report.records[0].web_metrics.comfort_score is not None
    assert report.records[0].web_metrics.action_clarity is not None
    assert report.web_summary is not None
    assert report.web_summary.evaluated_sample_count == 1


def test_fusion_dataset_baseline_specs_expose_year_and_reference():
    specs = build_fusion_dataset_baseline_specs()
    spec_by_id = {spec.baseline_id: spec for spec in specs}

    assert spec_by_id["rule_keyword"].year == 2025
    assert spec_by_id["rule_keyword"].display_name
    assert spec_by_id["agentic_hybrid_memory"].is_reference is True


def test_fusion_baseline_comparison_report_runs_on_synthetic_fusion_row(tmp_path):
    row = {
        "sample_id": "fusion-sample-1",
        "state_id": "state-1",
        "task_id": "task-1",
        "target_actions_json": '[{"domain":"light","service_name_norm":"turn_on","arguments_json":{"state":"on"}}]',
        "label_quality": "strong",
        "split": "test",
        "task_source": "user_nl",
        "raw_text": "Turn on the living room light",
        "parsed_slots_json": '{"device":"light","room":"living_room"}',
        "trigger_json": '{"type":"voice"}',
        "source_dataset": "home_assistant_datasets",
        "snapshot_ts": "2026-04-10T20:00:00+08:00",
        "occupancy_status": "occupied",
        "sensor_summary_json": "{}",
        "device_state_json": '{"light.living_room_light": {"attributes": {"brightness": 0}, "state": "off"}}',
        "environment_json": "{}",
        "history_action_summary_json": "[]",
    }

    report = build_fusion_baseline_comparison_report(
        rows=[row],
        output_dir=tmp_path / "fusion_baselines",
        baseline_ids=["rule_keyword", "agentic_no_memory"],
        current_primary_memory_backend="none",
        llm_enabled=False,
        show_progress=False,
    )

    baseline_ids = {item.baseline_id for item in report.baselines}
    table_ids = {item.system_id for item in report.comparison_table}
    assert report.sample_count == 1
    assert report.current_system.system_id == "current_system"
    assert "rule_keyword" in baseline_ids
    assert "agentic_no_memory" in baseline_ids
    assert "current_system" in table_ids
    assert "rule_keyword" in table_ids
    assert report.comparison_table_markdown.startswith("| system_id |")
    assert report.best_by_metric
