# Data Profile

## Raw Files
- aras: 0
- casas: 83
- edgewisepersona: 12
- fluent: 0
- home_assistant: 47039
- smartsense: 26
- zh_commands: 14

## Staging Tables
- source_manifest: 47176 rows
- stg_casas_activity_label: 1358388 rows
- stg_casas_event: 26348623 rows
- stg_edge_character: 200 rows
- stg_edge_routine: 797 rows
- stg_edge_session: 10000 rows
- stg_ha_area: 546 rows
- stg_ha_assist_record: 63 rows
- stg_ha_automation_record: 4 rows
- stg_ha_device: 1221 rows
- stg_ha_entity: 475 rows
- stg_ha_home: 71 rows
- stg_smartsense_dict: 1201 rows
- stg_smartsense_log_action: 3733790 rows
- stg_smartsense_routine_device: 84740 rows
- stg_zh_command: 7118 rows

## Canonical Tables
- dim_area: 705 rows
- dim_device: 2291 rows
- dim_entity: 2343 rows
- dim_home: 357 rows
- dim_user: 204 rows
- fact_action_item: 383141 rows
- fact_action_set: 381431 rows
- fact_state_snapshot: 3351343 rows
- fact_task: 412353 rows

## Bridge Tables
- bridge_episode_source: 380630 rows
- bridge_state_sensor_event: 76436787 rows
- bridge_task_candidate_device: 4055527 rows
- synthetic_discussion: 1236897 rows

## Episodes
- episodes: 381427 rows
- label_quality counts: {"strong": 373512, "medium": 7118, "weak": 797}
- split counts: {"train": 306621, "valid": 37423, "test": 37383}
