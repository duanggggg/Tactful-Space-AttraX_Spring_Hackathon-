"""Canonical warehouse schema definitions for smart-home episode datasets."""

from __future__ import annotations

from dataclasses import dataclass, field


ROOM_ENUM = [
    "living_room",
    "bedroom",
    "kitchen",
    "bathroom",
    "office",
    "entry",
    "garage",
    "outdoor",
    "other",
]

DEVICE_DOMAIN_ENUM = [
    "light",
    "climate",
    "fan",
    "switch",
    "cover",
    "media_player",
    "vacuum",
    "lock",
    "sensor",
    "appliance",
    "other",
]

ACTION_ENUM = [
    "turn_on",
    "turn_off",
    "toggle",
    "set_temperature",
    "set_humidity",
    "set_brightness",
    "open",
    "close",
    "lock",
    "unlock",
    "play",
    "pause",
    "stop",
    "start",
    "custom",
]

TASK_SOURCE_ENUM = [
    "user_nl",
    "schedule",
    "automation",
    "routine",
    "voice",
    "inferred",
]

LABEL_QUALITY_ENUM = ["strong", "medium", "weak", "mixed"]

CANDIDATE_SOURCE_ENUM = [
    "explicit_mention",
    "room_match",
    "routine_cooccur",
    "history_cooccur",
    "ha_inventory",
    "synthetic",
]


@dataclass(frozen=True)
class TableSpec:
    """Declarative schema metadata for one warehouse table."""

    name: str
    columns: list[str]
    primary_key: list[str] = field(default_factory=list)
    foreign_keys: list[str] = field(default_factory=list)


TABLE_SPECS: dict[str, TableSpec] = {
    "source_manifest": TableSpec(
        name="source_manifest",
        columns=[
            "source_dataset",
            "source_subdataset",
            "source_path",
            "file_name",
            "file_format",
            "download_method",
            "license",
            "sha256",
            "ingest_time",
            "status",
            "notes",
        ],
        primary_key=["source_dataset", "source_subdataset", "file_name"],
    ),
    "stg_ha_home": TableSpec(
        name="stg_ha_home",
        columns=[
            "ha_home_id",
            "home_name",
            "country_code",
            "location_desc",
            "home_type",
            "amenities_json",
            "source_file",
        ],
        primary_key=["ha_home_id"],
    ),
    "stg_ha_area": TableSpec(
        name="stg_ha_area",
        columns=["ha_home_id", "area_name", "area_order", "source_file"],
        primary_key=["ha_home_id", "area_name"],
    ),
    "stg_ha_device": TableSpec(
        name="stg_ha_device",
        columns=[
            "ha_home_id",
            "area_name",
            "device_name",
            "device_type_raw",
            "model_raw",
            "manufacturer_raw",
            "source_file",
        ],
        primary_key=["ha_home_id", "area_name", "device_name"],
    ),
    "stg_ha_entity": TableSpec(
        name="stg_ha_entity",
        columns=[
            "ha_home_id",
            "area_name",
            "device_name",
            "entity_id",
            "entity_domain",
            "source_file",
        ],
        primary_key=["entity_id"],
    ),
    "stg_ha_assist_record": TableSpec(
        name="stg_ha_assist_record",
        columns=[
            "ha_record_id",
            "dataset_name",
            "category",
            "sentence_list_json",
            "setup_json",
            "expect_changes_json",
            "ignore_changes_json",
            "fixture_home_ref",
            "source_file",
        ],
        primary_key=["ha_record_id"],
    ),
    "stg_ha_automation_record": TableSpec(
        name="stg_ha_automation_record",
        columns=[
            "automation_id",
            "problem_readme",
            "expected_result_json",
            "test_logic_ref",
            "fixture_home_ref",
            "source_file",
        ],
        primary_key=["automation_id"],
    ),
    "stg_smartsense_dict": TableSpec(
        name="stg_smartsense_dict",
        columns=["region_or_country", "dict_type", "raw_id", "raw_name"],
        primary_key=["region_or_country", "dict_type", "raw_id"],
    ),
    "stg_smartsense_log_action": TableSpec(
        name="stg_smartsense_log_action",
        columns=[
            "log_instance_id",
            "step_index",
            "region_or_country",
            "day_of_week_id",
            "hour_id",
            "device_id_raw",
            "control_id_raw",
            "device_control_id_raw",
            "split",
            "source_file",
        ],
        primary_key=["log_instance_id", "step_index"],
    ),
    "stg_smartsense_routine_device": TableSpec(
        name="stg_smartsense_routine_device",
        columns=[
            "routine_id",
            "region_or_country",
            "sequence_index",
            "device_id_raw",
            "source_file",
        ],
        primary_key=["routine_id", "sequence_index"],
    ),
    "stg_casas_event": TableSpec(
        name="stg_casas_event",
        columns=[
            "casas_home_id",
            "event_ts",
            "sensor_id_raw",
            "message_raw",
            "sensor_room_hint",
            "sensor_type_hint",
            "source_file",
        ],
        primary_key=["casas_home_id", "event_ts", "sensor_id_raw", "message_raw"],
    ),
    "stg_casas_activity_label": TableSpec(
        name="stg_casas_activity_label",
        columns=[
            "casas_home_id",
            "start_ts",
            "end_ts",
            "activity_label_raw",
            "source_file",
        ],
        primary_key=["casas_home_id", "start_ts", "end_ts", "activity_label_raw"],
    ),
    "stg_edge_character": TableSpec(
        name="stg_edge_character",
        columns=["persona_id", "persona_json", "source_file"],
        primary_key=["persona_id"],
    ),
    "stg_edge_routine": TableSpec(
        name="stg_edge_routine",
        columns=[
            "persona_id",
            "routine_id",
            "trigger_json",
            "action_json",
            "routine_text",
            "source_file",
        ],
        primary_key=["routine_id"],
    ),
    "stg_edge_session": TableSpec(
        name="stg_edge_session",
        columns=[
            "persona_id",
            "session_id",
            "session_type",
            "dialogue_json",
            "ground_truth_routine_ids_json",
            "source_file",
        ],
        primary_key=["session_id"],
    ),
    "stg_zh_command": TableSpec(
        name="stg_zh_command",
        columns=[
            "zh_record_id",
            "dataset_name",
            "raw_input_text",
            "raw_output_json",
            "source_file",
        ],
        primary_key=["zh_record_id"],
    ),
    "dim_home": TableSpec(
        name="dim_home",
        columns=[
            "home_sk",
            "home_source",
            "source_home_id",
            "home_name",
            "country_code",
            "location_desc",
            "home_type",
            "is_synthetic",
            "source_dataset",
        ],
        primary_key=["home_sk"],
    ),
    "dim_area": TableSpec(
        name="dim_area",
        columns=["area_sk", "home_sk", "area_name_raw", "area_name_norm", "area_type"],
        primary_key=["area_sk"],
        foreign_keys=["home_sk -> dim_home.home_sk"],
    ),
    "dim_device": TableSpec(
        name="dim_device",
        columns=[
            "device_sk",
            "home_sk",
            "area_sk",
            "device_name_raw",
            "device_name_norm",
            "device_domain",
            "device_type_raw",
            "manufacturer_raw",
            "model_raw",
            "source_dataset",
        ],
        primary_key=["device_sk"],
        foreign_keys=["home_sk -> dim_home.home_sk", "area_sk -> dim_area.area_sk"],
    ),
    "dim_entity": TableSpec(
        name="dim_entity",
        columns=["entity_sk", "device_sk", "entity_id", "entity_domain", "entity_name_norm"],
        primary_key=["entity_sk"],
        foreign_keys=["device_sk -> dim_device.device_sk"],
    ),
    "dim_user": TableSpec(
        name="dim_user",
        columns=["user_sk", "source_user_id", "user_type", "persona_profile_json", "source_dataset"],
        primary_key=["user_sk"],
    ),
    "fact_state_snapshot": TableSpec(
        name="fact_state_snapshot",
        columns=[
            "state_id",
            "home_sk",
            "user_sk",
            "snapshot_ts",
            "snapshot_granularity",
            "occupancy_status",
            "active_area_sk",
            "activity_hint",
            "sensor_summary_json",
            "device_state_json",
            "environment_json",
            "history_action_summary_json",
            "source_dataset",
            "label_quality",
        ],
        primary_key=["state_id"],
    ),
    "fact_task": TableSpec(
        name="fact_task",
        columns=[
            "task_id",
            "home_sk",
            "user_sk",
            "task_ts",
            "task_source",
            "raw_text",
            "normalized_text",
            "parsed_slots_json",
            "trigger_json",
            "priority",
            "target_area_sk",
            "source_dataset",
            "label_quality",
        ],
        primary_key=["task_id"],
    ),
    "fact_action_set": TableSpec(
        name="fact_action_set",
        columns=[
            "action_set_id",
            "task_id",
            "home_sk",
            "action_ts",
            "action_reason_type",
            "action_count",
            "source_dataset",
            "label_quality",
        ],
        primary_key=["action_set_id"],
    ),
    "fact_action_item": TableSpec(
        name="fact_action_item",
        columns=[
            "action_item_id",
            "action_set_id",
            "device_sk",
            "entity_sk",
            "device_domain",
            "service_name_norm",
            "arguments_json",
            "target_state_json",
            "sequence_index",
            "source_dataset",
        ],
        primary_key=["action_item_id"],
    ),
    "bridge_state_sensor_event": TableSpec(
        name="bridge_state_sensor_event",
        columns=["state_id", "casas_home_id", "event_ts", "sensor_id_raw", "message_raw"],
        primary_key=["state_id", "event_ts", "sensor_id_raw", "message_raw"],
    ),
    "bridge_task_candidate_device": TableSpec(
        name="bridge_task_candidate_device",
        columns=[
            "task_id",
            "device_sk",
            "candidate_rank",
            "candidate_source",
            "candidate_score",
        ],
        primary_key=["task_id", "device_sk", "candidate_source"],
    ),
    "bridge_episode_source": TableSpec(
        name="bridge_episode_source",
        columns=["sample_id", "source_dataset", "source_record_id", "source_role"],
        primary_key=["sample_id", "source_dataset", "source_record_id", "source_role"],
    ),
    "synthetic_discussion": TableSpec(
        name="synthetic_discussion",
        columns=[
            "discussion_id",
            "task_id",
            "device_sk",
            "proposal_text",
            "proposal_action_json",
            "proposal_confidence",
            "proposal_type",
            "is_synthetic",
        ],
        primary_key=["discussion_id"],
    ),
    "episodes": TableSpec(
        name="episodes",
        columns=[
            "sample_id",
            "home_sk",
            "user_sk",
            "state_id",
            "task_id",
            "action_set_id",
            "sample_ts",
            "candidate_devices_json",
            "target_actions_json",
            "synthetic_discussion_json",
            "source_mix_json",
            "label_quality",
            "split",
        ],
        primary_key=["sample_id"],
    ),
}
