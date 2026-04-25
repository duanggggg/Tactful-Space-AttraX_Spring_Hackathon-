# 数据集验证坏例对比

数据来源：
- `outputs/dataset_eval_smoke/records.csv`
- `data_processed/episodes.parquet`
- `data_processed/fact_task.parquet`
- `outputs/dataset_eval_smoke/memory/records/*.json`

## 一页结论

当前效果不佳主要集中在三类问题：

1. `Home Assistant` 的自然语言任务存在明显过激活，单一媒体控制任务会唤醒几乎所有 agent。
2. `SmartSense` 的历史动作推断任务容易被错误路由到环境舒适类 agent，出现“看电视历史 -> 开空调”的错判。
3. `EdgeWisePersona` 的 routine 任务虽然能部分命中目标模态，但会额外生成大量无关动作，导致动作集合严重膨胀。

同时需要注意：

- 当前离线评测脚本对 `target_actions_json` 的 gold 字段读取，使用的是 `domain`，而数据仓库里的真实字段是 `device_domain`。
- 因此不少样本在评测记录里会被记成 `gold_domains_json = ['other']`，这会额外压低 `domain/action F1`。
- 所以当前低分里既有真实系统问题，也有评测归一化偏差。

## 代表性坏例

| Case | Sample | Source | Task | Gold | Pred | 主要问题 |
| --- | --- | --- | --- | --- | --- | --- |
| A | `b1f9f0...` | home_assistant_datasets | `Turn the volume down to 50%` | 1 个 `media_player` 动作 | 8 个跨域动作 | 自然语言任务被错误扩散成全屋协同 |
| B | `0026e48...` | smartsense | `Recent activity involved SetTop, Television, Television` | 1 个 `media_player` 动作 | 3 个 `climate` 动作 | 历史行为理解错误，误唤醒 `cooling_agent` |
| C | `0d788cc...` | edgewisepersona | 午后 routine | 3 个目标动作 | 8 个动作 | routine 触发后出现多 agent 过生成 |

## Case A: Home Assistant 自然语言任务过激活

样本信息：

- `sample_id`: `b1f9f0b69845dddfa0694584ae5e0d8543ebbe93`
- `source_dataset`: `home_assistant_datasets`
- `task_source`: `user_nl`
- `raw_text`: `Turn the volume down to 50%`

关键指标：

- `wakeup_agent_f1 = 0.0`
- `final_service_f1 = 0.4`
- `final_action_f1 = 0.0`
- `action_count_abs_error = 7`
- `gold_action_count = 1`
- `predicted_action_count = 8`

Gold / Pred 对比：

- Gold agent: 评测记录中为空；结合任务语义应为 `music_agent`
- Pred agents:
  - `cooling_agent`
  - `lighting_agent`
  - `music_agent`
  - `fan_agent`
  - `cover_agent`
  - `lock_agent`
  - `switch_agent`
  - `appliance_agent`
- Gold action:
  - `media_player`，参数 `{"volume_level": 0.5}`
- Pred actions:
  - `living_room_ac_1.power = true`
  - `living_room_ac_1.target_temperature = 25`
  - `living_room_ac_1.fan_speed = medium`
  - `living_room_main.power = true`
  - `living_room_main.brightness = 65`
  - `living_room_fan_1.power = true`
  - `living_room_fan_1.speed = medium`
  - `living_room_fan_1.oscillate = true`

结论：

- 这是最典型的“单设备媒体控制任务，被扩展成全屋舒适场景”的错误。
- 从系统行为上看，task routing 太松，scene-level heuristic 压过了 explicit command。

## Case B: SmartSense 历史行为误判到错误 agent

样本信息：

- `sample_id`: `0026e48e839d47f98bbcb4d853dea04b02deab23`
- `source_dataset`: `smartsense`
- `task_source`: `inferred`
- `task_summary`: `Decide the next smart-home action based on recent home activity. Recent activity involved SetTop, Television, Television.`

关键指标：

- `wakeup_agent_f1 = 0.0`
- `final_service_f1 = 0.5`
- `final_action_f1 = 0.0`
- `action_count_abs_error = 2`
- `gold_action_count = 1`
- `predicted_action_count = 3`

Gold / Pred 对比：

- Gold agent: 评测记录中为 `music_agent`
- Pred agents:
  - `cooling_agent`
- Gold action:
  - `media_player`，`device_control_id_raw = 245`
- Pred actions:
  - `living_room_ac_1.power = true`
  - `living_room_ac_1.target_temperature = 25`
  - `living_room_ac_1.fan_speed = medium`

结论：

- 历史序列里已经出现 `SetTop / Television`，但系统仍将任务解释为“房间偏热，需要制冷”。
- 说明当前历史上下文到 agent/domain 的映射还过度依赖默认环境启发，而没有充分利用行为序列语义。

## Case C: EdgeWisePersona routine 多 agent 过生成

样本信息：

- `sample_id`: `0d788cc4ea1448840deb8ade4124210939570b2f`
- `source_dataset`: `edgewisepersona`
- `task_source`: `routine`
- `raw_text`: `Routine with triggers {"time_of_day": "afternoon", "day_of_week": "weekday", "sun_phase": "daylight", "weather": "sunny", "outdoor_temp": "warm"} and actions {"tv": null, "ac": {"temperature": 22, "mode": "cool", "fan_speed": 1}, "lights": {"brightness": 75, "color": "neutral", "mode": "static"}, "speaker": {"volume": 30, "equalizer": "balanced"}, "security": null}`

关键指标：

- `wakeup_agent_f1 = 0.333`
- `final_service_f1 = 0.4`
- `final_action_f1 = 0.0`
- `action_count_abs_error = 5`
- `gold_action_count = 3`
- `predicted_action_count = 8`

Gold / Pred 对比：

- Gold agents: 评测记录里只保留了 `music_agent`，但从动作内容看实际应覆盖 `climate + light + media_player`
- Pred agents:
  - `cooling_agent`
  - `lighting_agent`
  - `music_agent`
  - `fan_agent`
  - `lock_agent`
- Gold actions:
  - AC: `temperature = 22, mode = cool, fan_speed = 1`
  - Light: `brightness = 75, color = neutral`
  - Speaker: `volume = 30, equalizer = balanced`
- Pred actions:
  - AC 3 条动作
  - Light 2 条动作
  - Fan 3 条动作

结论：

- 系统能命中 routine 的一部分真实模态，但会额外激活 `fan_agent`、`lock_agent` 等无关模块。
- 这类问题会直接拉高 `avg_conflict_count` 和 `avg_predicted_action_count`，也是当前最终动作集合偏大的核心原因。

## PPT 可直接讲的总结句

1. 当前不是“完全不会做”，而是“会做一部分，但很容易过度唤醒、过度生成”。
2. `SmartSense` 暴露的是历史行为理解问题，`Home Assistant` 暴露的是显式指令优先级不足，`EdgeWisePersona` 暴露的是 routine 合并时的动作膨胀。
3. 目前 `final_action_f1 = 0` 不能被直接解读为系统完全失效，因为评测脚本还存在 `device_domain -> domain` 的 gold 归一化偏差，需要修正后再看更可信的动作级指标。
