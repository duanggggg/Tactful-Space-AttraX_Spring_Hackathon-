# 智能家居多 Agent 系统评价指标设计

本文档用于总结当前智能家居多 Agent 系统中的评价指标设计，供后续实现、重构或交给 Codex 生成代码使用。

---

## 1. 系统背景

当前系统包含以下核心流程：

```text
当前室内状态 + 用户需求（可选）
        ↓
中枢节点激活相关 agent
        ↓
agent 从知识图谱中检索相关记忆
        ↓
agent 之间展开讨论与协商
        ↓
每个 agent 得到自己的 action
        ↓
执行 / 模拟执行
        ↓
结果归档回知识图谱
```

当前保留的房间：

```text
living_room
bedroom
```

当前保留的 agent：

```text
air_conditioner
window
curtain
fan
fresh_air
dehumidifier
light
computer
```

当前保留的环境变量：

```text
temperature
humidity
air
brightness
noise
energy
```

---

## 2. 总体评价目标

系统评价指标分为两层：

1. **系统整体舒适度评价**
   - 判断最终环境是否更舒适。
   - 判断是否满足用户需求。
   - 判断是否避免了能耗浪费、冲突和频繁波动。

2. **Agent action 选取评价**
   - 判断每个 agent 的 action 是否合理。
   - 判断 action 是否必要、低冲突、低成本、可解释。
   - 判断 action 之间是否形成协同或冲突。

---

## 3. 总体评价公式

可以将系统整体得分定义为：

```text
SystemScore =
α × ComfortScore
+ β × DemandSatisfaction
+ γ × CoordinationScore
+ δ × ActionQuality
+ ε × MemoryQuality
- η × EnergyCost
- θ × InstabilityPenalty
```

其中：

| 指标 | 含义 |
|---|---|
| `ComfortScore` | 当前房间整体舒适度 |
| `DemandSatisfaction` | 用户需求满足度 |
| `CoordinationScore` | agent 间协调质量 |
| `ActionQuality` | action 质量 |
| `MemoryQuality` | 知识图谱记忆检索与归档质量 |
| `EnergyCost` | 能耗代价 |
| `InstabilityPenalty` | 频繁切换、环境波动带来的惩罚 |

---

## 4. 有无用户需求时的权重区别

### 4.1 无明确用户需求

当用户没有输入需求时，系统主要依赖当前环境状态和默认场景推断。

```text
SystemScore =
0.45 × ComfortScore
+ 0.20 × CoordinationScore
+ 0.15 × ActionQuality
+ 0.10 × MemoryQuality
- 0.05 × EnergyCost
- 0.05 × InstabilityPenalty
```

此时系统更强调：

- 环境状态是否舒适
- agent 是否协调
- action 是否必要
- 是否避免无意义能耗

---

### 4.2 有明确用户需求

当用户输入明确需求时，例如：

```text
我想在客厅看电影
我准备睡觉，但是有点闷
卧室太潮了
```

此时用户需求满足度权重提高：

```text
SystemScore =
0.30 × ComfortScore
+ 0.30 × DemandSatisfaction
+ 0.15 × CoordinationScore
+ 0.15 × ActionQuality
+ 0.05 × MemoryQuality
- 0.03 × EnergyCost
- 0.02 × InstabilityPenalty
```

此时系统更强调：

- 是否满足用户当前意图
- 是否为了用户意图调整场景权重
- 舒适度和能耗不再完全平均，而是服从用户目标

---

## 5. 房间级舒适度评价

每个房间的舒适度可以定义为：

```text
RoomScore(room) =
Σ ParameterWeight(room, parameter, scene, demand)
× ParameterSatisfaction(room, parameter)
```

当前房间：

```text
living_room
bedroom
```

当前参数：

```text
temperature
humidity
air
brightness
noise
energy
```

整体舒适度：

```text
ComfortScore =
Σ RoomWeight(room) × RoomScore(room)
```

---

## 6. 默认房间参数权重

### 6.1 客厅默认权重

客厅偏向活动、娱乐、会客与通风体验。

| 参数 | 权重 |
|---|---:|
| `air` | 0.22 |
| `temperature` | 0.20 |
| `brightness` | 0.18 |
| `noise` | 0.16 |
| `humidity` | 0.14 |
| `energy` | 0.10 |

---

### 6.2 卧室默认权重

卧室偏向睡眠、安静、温度稳定和长时间低能耗运行。

| 参数 | 权重 |
|---|---:|
| `noise` | 0.25 |
| `temperature` | 0.22 |
| `air` | 0.18 |
| `humidity` | 0.16 |
| `brightness` | 0.12 |
| `energy` | 0.07 |

---

## 7. 参数级评价指标

### 7.1 温度 `temperature`

相关 agent：

```text
air_conditioner
window
curtain
fan
fresh_air
dehumidifier
computer
```

核心指标：

| 指标 | 含义 |
|---|---|
| `temp_deviation` | 当前温度与目标温度的偏差 |
| `temp_change_speed` | 温度变化速度是否过快 |
| `temp_stability` | 温度是否稳定 |
| `perceived_temp_score` | 体感温度是否舒适 |

简单评分：

```text
temperature_score =
1 - abs(current_temperature - target_temperature) / allowed_temperature_range
```

建议将最终值裁剪到 `[0, 1]`。

体感温度可考虑：

```text
perceived_temperature =
actual_temperature
+ humidity_effect
- fan_cooling_effect
+ sunlight_heat_effect
+ device_heat_effect
```

---

### 7.2 湿度 `humidity`

相关 agent：

```text
dehumidifier
air_conditioner
fresh_air
window
fan
```

核心指标：

| 指标 | 含义 |
|---|---|
| `humidity_deviation` | 湿度偏离舒适区间的程度 |
| `humidity_trend` | 湿度是在改善还是恶化 |
| `dehumidification_efficiency` | 除湿动作是否有效 |
| `over_dry_penalty` | 是否过度除湿 |

推荐舒适区间：

```text
40% <= humidity <= 60%
```

评分逻辑：

```text
if humidity in [40, 60]:
    humidity_score = 1
elif humidity > 60:
    humidity_score = 1 - (humidity - 60) / tolerance
else:
    humidity_score = 1 - (40 - humidity) / tolerance
```

典型冲突：

```text
dehumidifier_on + window_open + outdoor_humidity_high
```

---

### 7.3 空气 `air`

空气可以先作为综合指标，后续再拆分。

可拆分为：

```text
co2_score
pm25_score
voc_score
odor_score
ventilation_score
```

相关 agent：

```text
fresh_air
window
air_conditioner
fan
dehumidifier
```

综合评分示例：

```text
air_score =
0.4 × co2_score
+ 0.3 × pm25_score
+ 0.2 × voc_score
+ 0.1 × odor_score
```

如果暂时没有多种传感器，可先使用：

```text
air_score = f(indoor_air_quality, outdoor_air_quality, ventilation_state)
```

典型冲突：

| 动作 | 副作用 |
|---|---|
| `window_open` | 噪音上升、温度波动、湿度波动 |
| `fresh_air_high` | 能耗上升、噪音上升、温湿度波动 |
| `fan_on` | 只能改善空气流动感，不能真正降低 CO2 |

---

### 7.4 亮度 `brightness`

相关 agent：

```text
light
curtain
window
computer
```

核心指标：

| 指标 | 含义 |
|---|---|
| `brightness_deviation` | 当前亮度与目标亮度的偏差 |
| `glare_penalty` | 是否眩光 |
| `screen_visibility_score` | 视频/电脑画面是否清晰 |
| `natural_light_usage` | 是否优先利用自然光 |
| `scene_match_score` | 是否符合当前场景 |

场景示例：

| 场景 | 亮度目标 |
|---|---|
| 客厅会客 | 中高亮度 |
| 客厅观影 | 低亮度，避免屏幕反光 |
| 卧室睡前 | 低亮度、柔和 |
| 卧室起夜 | 极低亮度，但保证安全 |
| 白天休闲 | 优先自然光 |

评分示例：

```text
brightness_score =
1 - abs(current_brightness - target_brightness) / allowed_brightness_range
```

---

### 7.5 噪音 `noise`

相关 agent：

```text
computer
fan
fresh_air
air_conditioner
dehumidifier
window
```

注意：电脑播放音乐或视频产生的声音不一定是负面噪音。

因此需要区分：

```text
desired_sound
undesired_noise
```

评分可以写成：

```text
noise_score =
desired_sound_quality - undesired_noise_penalty
```

核心指标：

| 指标 | 含义 |
|---|---|
| `noise_level` | 当前总噪音大小 |
| `device_noise_penalty` | 设备运行噪音 |
| `outdoor_noise_penalty` | 外界噪音 |
| `media_clarity_score` | 音乐/视频是否清晰 |
| `sleep_noise_score` | 睡眠场景下是否安静 |

场景差异：

| 场景 | 噪音评价重点 |
|---|---|
| 客厅播放视频 | 设备噪音不能盖过视频声音 |
| 客厅聊天 | 背景噪音不能影响交谈 |
| 卧室睡觉 | 新风、除湿机、风扇都要低噪 |
| 卧室白噪音 | 电脑播放白噪音可能是正向声音 |

---

### 7.6 能耗 `energy`

相关 agent：

```text
air_conditioner
fresh_air
dehumidifier
light
computer
fan
window
curtain
```

核心指标：

| 指标 | 含义 |
|---|---|
| `total_energy` | 总能耗 |
| `redundant_energy` | 冗余能耗 |
| `energy_efficiency` | 单位舒适度提升所需能耗 |
| `peak_power_penalty` | 是否出现高功率叠加 |
| `natural_resource_usage` | 是否优先利用自然通风 / 自然光 |

能效评价：

```text
energy_efficiency =
comfort_improvement / energy_cost
```

典型冗余：

```text
air_conditioner_on + window_open
dehumidifier_on + window_open + outdoor_humidity_high
fresh_air_high + window_open
light_high + outdoor_brightness_sufficient + curtain_open
```

---

## 8. Agent Action 评价

每个 agent 的 action 可以用以下函数评价：

```text
ActionValue(action) =
ExpectedComfortImprovement(action)
- EnergyCost(action)
- NoiseCost(action)
- ConflictCost(action)
- UncertaintyCost(action)
- RedundancyCost(action)
```

更形式化：

```text
U(a_i) =
ΔComfort(a_i)
- C_energy(a_i)
- C_noise(a_i)
- C_conflict(a_i)
- C_uncertainty(a_i)
- C_redundancy(a_i)
```

---

## 9. 各 Agent 的 Action 评价重点

### 9.1 空调 `air_conditioner`

可选 action：

```text
cooling
heating
set_target_temperature
set_fan_speed
turn_off
```

影响变量：

```text
temperature
humidity
energy
noise
```

重点评价：

| 指标 | 含义 |
|---|---|
| `temp_improvement` | 是否让温度接近目标 |
| `humidity_side_effect` | 是否过度除湿 |
| `energy_cost` | 能耗是否过高 |
| `noise_cost` | 风速噪音是否可接受 |
| `window_conflict` | 是否与开窗冲突 |
| `fresh_air_conflict` | 是否与新风冲突 |

典型扣分：

```text
air_conditioner_cooling + window_open
air_conditioner_high_fan + bedroom_sleep_scene
```

---

### 9.2 窗户 `window`

可选 action：

```text
open
close
half_open
keep
```

影响变量：

```text
air
temperature
humidity
noise
brightness
energy
```

重点评价：

| 指标 | 含义 |
|---|---|
| `ventilation_gain` | 通风收益 |
| `outdoor_air_risk` | 室外空气风险 |
| `outdoor_noise_risk` | 室外噪音风险 |
| `thermal_loss` | 对温度造成的损失 |
| `humidity_loss` | 对湿度造成的损失 |
| `air_conditioner_conflict` | 是否与空调冲突 |

典型扣分：

```text
outdoor_air_bad + window_open
outdoor_noise_high + bedroom_sleep_scene + window_open
air_conditioner_on + window_open
```

---

### 9.3 窗帘 `curtain`

可选 action：

```text
open
close
half_open
adjust_angle
keep
```

影响变量：

```text
brightness
temperature
energy
```

重点评价：

| 指标 | 含义 |
|---|---|
| `brightness_gain` | 是否改善亮度 |
| `glare_penalty` | 是否造成眩光 |
| `screen_visibility_gain` | 是否提升视频观看体验 |
| `solar_heat_gain` | 是否造成日晒升温 |
| `lighting_energy_saving` | 是否减少开灯需求 |

典型扣分：

```text
movie_scene + curtain_open + screen_glare_high
summer_strong_sunlight + curtain_open + room_temperature_high
```

---

### 9.4 风扇 `fan`

可选 action：

```text
turn_on
set_speed
turn_off
oscillate
direct_blow
```

影响变量：

```text
perceived_temperature
noise
energy
air_flow
```

重点评价：

| 指标 | 含义 |
|---|---|
| `perceived_cooling_gain` | 体感降温收益 |
| `noise_cost` | 噪音代价 |
| `energy_cost` | 能耗代价 |
| `air_conditioner_substitution_gain` | 是否可以降低空调负担 |
| `sleep_disturbance` | 是否影响睡眠 |

典型扣分：

```text
bedroom_sleep_scene + fan_high_speed
video_scene + fan_noise_high
```

---

### 9.5 新风 `fresh_air`

可选 action：

```text
turn_on
increase_airflow
decrease_airflow
turn_off
```

影响变量：

```text
air
temperature
humidity
noise
energy
```

重点评价：

| 指标 | 含义 |
|---|---|
| `air_quality_gain` | 空气改善收益 |
| `thermal_side_effect` | 温度副作用 |
| `humidity_side_effect` | 湿度副作用 |
| `noise_cost` | 风机噪音 |
| `energy_cost` | 能耗 |
| `window_redundancy` | 是否与开窗重复 |

典型扣分：

```text
fresh_air_high + bedroom_sleep_scene
fresh_air_high + outdoor_humidity_high
fresh_air_high + window_open + air_quality_already_good
```

---

### 9.6 除湿机 `dehumidifier`

可选 action：

```text
turn_on
set_level
turn_off
timer_dehumidify
```

影响变量：

```text
humidity
temperature
noise
energy
```

重点评价：

| 指标 | 含义 |
|---|---|
| `humidity_gain` | 湿度改善收益 |
| `over_dry_risk` | 过度除湿风险 |
| `noise_cost` | 噪音代价 |
| `energy_cost` | 能耗代价 |
| `window_conflict` | 是否与开窗冲突 |
| `fresh_air_conflict` | 是否与新风冲突 |

典型扣分：

```text
dehumidifier_on + window_open + outdoor_humidity_high
bedroom_night_scene + dehumidifier_high_level
```

---

### 9.7 灯光 `light`

可选 action：

```text
turn_on
turn_off
dim_up
dim_down
set_color_temperature
```

影响变量：

```text
brightness
energy
```

重点评价：

| 指标 | 含义 |
|---|---|
| `brightness_gain` | 亮度改善 |
| `scene_match` | 是否符合当前场景 |
| `screen_conflict` | 是否影响视频观看 |
| `energy_cost` | 照明能耗 |
| `natural_light_redundancy` | 是否在自然光足够时开灯 |

典型扣分：

```text
outdoor_brightness_sufficient + curtain_open + light_high
movie_scene + light_high
bedroom_sleep_scene + light_not_dimmed
```

---

### 9.8 电脑 `computer`

可选 action：

```text
play_music
play_video
adjust_volume
adjust_screen_brightness
pause_media
sleep_mode
```

影响变量：

```text
noise
brightness
energy
temperature
```

重点评价：

| 指标 | 含义 |
|---|---|
| `media_satisfaction` | 是否满足娱乐需求 |
| `volume_suitability` | 音量是否合适 |
| `screen_visibility` | 屏幕是否清晰 |
| `noise_interference` | 是否干扰睡眠或其他活动 |
| `energy_cost` | 能耗 |
| `heat_generation` | 发热对温度的副作用 |

典型扣分：

```text
bedroom_sleep_scene + video_playing
movie_scene + screen_visibility_low
fan_noise_high + volume_forced_high
```

---

## 10. 冲突协调评价

### 10.1 硬冲突

硬冲突是原则上不应同时出现的动作。

| 冲突动作 | 原因 |
|---|---|
| `air_conditioner_cooling + window_open` | 能耗浪费，温度控制失败 |
| `dehumidifier_on + window_open + outdoor_humidity_high` | 除湿无效 |
| `bedroom_sleep + fresh_air_high + fan_high` | 噪音过高 |
| `movie_scene + light_high + curtain_open` | 屏幕体验差 |
| `outdoor_air_bad + window_open` | 引入污染 |

建议：

```text
hard_conflict_penalty = very_large
```

---

### 10.2 软冲突

软冲突不是绝对不能做，但需要扣分或权衡。

| 冲突动作 | 说明 |
|---|---|
| `fresh_air_on + air_conditioner_on` | 可以共存，但会增加空调负荷 |
| `fan_on + computer_video` | 可以共存，但风扇噪音可能影响声音 |
| `curtain_close + light_on` | 可以共存，但可能增加能耗 |
| `dehumidifier_on + air_conditioner_dry_mode` | 可以共存，但可能冗余 |

建议：

```text
soft_conflict_penalty = interaction_cost
```

---

### 10.3 协同收益

以下组合应给予加分。

| 协同动作 | 协同效果 |
|---|---|
| `curtain_close + air_conditioner_cooling` | 降低太阳热输入，提高制冷效率 |
| `fan_low + air_conditioner_moderate` | 提升体感，降低空调负担 |
| `curtain_close + computer_video` | 提升观影体验 |
| `fresh_air_low + air_conditioner_stable` | 保持空气质量和温度 |
| `light_dim + computer_video` | 更符合观影场景 |

建议：

```text
synergy_bonus = positive_interaction_gain
```

---

## 11. 讨论过程评价

由于系统是通过 agent 讨论得出任务，因此讨论过程也需要评价。

### 11.1 激活合理性

| 指标 | 含义 |
|---|---|
| `activation_precision` | 被激活的 agent 是否确实相关 |
| `activation_recall` | 是否漏掉了关键 agent |
| `activation_cost` | 是否激活了太多无关 agent |

示例：

```text
用户需求：我想在卧室睡觉，但有点闷
```

应该激活：

```text
fresh_air
window
air_conditioner
fan
dehumidifier
light
```

如果没有激活 `fresh_air` 或 `window`，说明 `activation_recall` 较低。

---

### 11.2 记忆检索质量

| 指标 | 含义 |
|---|---|
| `memory_relevance` | 检索到的信息是否和当前问题相关 |
| `memory_freshness` | 信息是否足够新 |
| `memory_consistency` | 是否与当前状态冲突 |
| `memory_usage_rate` | agent 是否真正使用了检索到的记忆 |
| `memory_noise_rate` | 检索到的无关记忆比例 |

高价值记忆示例：

```text
用户夜间不喜欢新风高档
用户看电影时偏好低亮度
卧室夜间除湿机高档会影响睡眠
```

---

### 11.3 讨论收敛质量

| 指标 | 含义 |
|---|---|
| `consensus_score` | agent 是否达成一致 |
| `conflict_resolution_score` | 冲突是否被明确解决 |
| `discussion_efficiency` | 是否用了过多轮讨论 |
| `argument_quality` | agent 是否基于环境变量和记忆提出理由 |
| `unresolved_conflict_count` | 还有多少冲突未解决 |

好的讨论结果：

```text
air_conditioner: low_power_cooling
curtain: close
fresh_air: low
fan: off
```

差的讨论结果：

```text
air_conditioner: cooling
window: open
dehumidifier: on
fresh_air: high
```

---

### 11.4 任务分配清晰度

| 指标 | 含义 |
|---|---|
| `action_clarity` | action 是否具体 |
| `action_parameter_completeness` | 是否包含档位、目标值、持续时间 |
| `responsibility_uniqueness` | 是否明确由哪个 agent 负责 |
| `fallback_defined` | 如果执行失败，是否有备选方案 |

不好的任务：

```text
空调调节一下温度
```

好的任务：

```text
air_conditioner:
  room: bedroom
  mode: cooling
  target_temperature: 26
  fan_speed: low
  duration: 30min
  reevaluate_after: 30min
```

---

## 12. 知识图谱归档评价

每次讨论和执行结果都应归档到知识图谱中，但需要控制质量，避免知识图谱膨胀和污染。

### 12.1 归档内容质量

| 指标 | 含义 |
|---|---|
| `archive_completeness` | 是否记录了状态、需求、讨论、动作、结果 |
| `archive_reusability` | 未来是否能复用 |
| `archive_specificity` | 是否足够具体 |
| `archive_redundancy` | 是否重复记录已有知识 |
| `archive_confidence` | 这条经验的可信度 |

建议每次归档至少包含：

```text
scene
room
state_before
user_demand
activated_agents
retrieved_memory
discussion_summary
final_actions
expected_effect
state_after
user_feedback
confidence
```

---

### 12.2 经验更新指标

执行后需要比较：

```text
predicted_effect vs actual_effect
```

核心指标：

| 指标 | 含义 |
|---|---|
| `prediction_error` | 预测误差 |
| `model_update_need` | 是否需要更新经验 |
| `experience_confidence_change` | 经验可信度上升或下降 |
| `repeated_failure_count` | 同类场景失败次数 |

示例：

```text
预测：30 分钟内卧室温度下降 2℃
实际：30 分钟内卧室温度只下降 0.8℃
```

应写回知识图谱：

```text
该卧室在当前外部温度和窗帘状态下，空调制冷效率低于预期。
```

---

## 13. 最终推荐指标体系

### 13.1 环境结果指标

| 指标 | 说明 |
|---|---|
| `comfort_score` | 总舒适度 |
| `room_score` | 单房间舒适度 |
| `parameter_score` | 单参数满意度 |
| `demand_satisfaction` | 用户需求满足度 |
| `comfort_improvement` | action 前后舒适度提升 |

---

### 13.2 Action 质量指标

| 指标 | 说明 |
|---|---|
| `expected_utility` | action 预期收益 |
| `actual_utility` | action 实际收益 |
| `energy_efficiency` | 单位能耗带来的舒适度提升 |
| `side_effect_cost` | 副作用成本 |
| `redundancy_score` | 是否冗余 |
| `necessity_score` | 是否必要 |
| `stability_score` | 是否避免频繁开关 |

---

### 13.3 冲突协调指标

| 指标 | 说明 |
|---|---|
| `hard_conflict_count` | 硬冲突数量 |
| `soft_conflict_cost` | 软冲突代价 |
| `synergy_bonus` | 协同收益 |
| `unresolved_conflict_count` | 未解决冲突数量 |
| `coordination_score` | 总体协调程度 |

---

### 13.4 讨论过程指标

| 指标 | 说明 |
|---|---|
| `activation_precision` | 激活 agent 是否准确 |
| `activation_recall` | 是否漏掉关键 agent |
| `memory_relevance` | 记忆检索是否相关 |
| `consensus_score` | 讨论是否达成共识 |
| `discussion_efficiency` | 讨论是否高效 |
| `action_clarity` | 任务是否清晰 |

---

### 13.5 知识图谱指标

| 指标 | 说明 |
|---|---|
| `archive_quality` | 归档质量 |
| `memory_reuse_rate` | 历史经验复用率 |
| `prediction_error` | 预测误差 |
| `knowledge_growth_quality` | 知识增长质量 |
| `stale_memory_rate` | 过时记忆比例 |
| `contradiction_rate` | 记忆之间的矛盾比例 |

---

## 14. 第一版优先实现指标

第一版不要实现过多指标，建议先实现以下 10 个：

| 优先级 | 指标 |
|---:|---|
| 1 | `comfort_score` |
| 2 | `demand_satisfaction` |
| 3 | `parameter_score` |
| 4 | `energy_cost` |
| 5 | `hard_conflict_count` |
| 6 | `soft_conflict_cost` |
| 7 | `action_utility` |
| 8 | `memory_relevance` |
| 9 | `action_clarity` |
| 10 | `prediction_error` |

最核心的闭环指标：

```text
comfort_score
action_utility
conflict_penalty
prediction_error
```

这四个指标可以支持系统形成闭环：

```text
当前状态
→ agent 讨论
→ action
→ 环境变化
→ 评价
→ 写回知识图谱
→ 下次决策更好
```

---

## 15. 推荐数据结构示例

```json
{
  "episode_id": "2026-04-24-bedroom-001",
  "room": "bedroom",
  "scene": "sleep_preparation",
  "user_demand": "感觉有点闷，准备睡觉",
  "state_before": {
    "temperature": 27.5,
    "humidity": 68,
    "air": 0.55,
    "brightness": 0.2,
    "noise": 0.3,
    "energy": 0.1
  },
  "activated_agents": [
    "air_conditioner",
    "window",
    "fresh_air",
    "dehumidifier",
    "fan",
    "light"
  ],
  "retrieved_memory": [
    {
      "content": "用户夜间不喜欢新风高档",
      "relevance": 0.92,
      "confidence": 0.85
    }
  ],
  "final_actions": {
    "fresh_air": {
      "action": "turn_on",
      "level": "low",
      "duration": "30min"
    },
    "dehumidifier": {
      "action": "turn_on",
      "level": "low",
      "target_humidity": 55
    },
    "window": {
      "action": "keep_closed"
    },
    "fan": {
      "action": "keep_off"
    },
    "air_conditioner": {
      "action": "cooling",
      "target_temperature": 26,
      "fan_speed": "low"
    }
  },
  "expected_score": {
    "comfort_score": 0.82,
    "demand_satisfaction": 0.87,
    "coordination_score": 0.90,
    "action_quality": 0.84,
    "memory_quality": 0.88
  },
  "state_after": {
    "temperature": 26.3,
    "humidity": 58,
    "air": 0.78,
    "brightness": 0.1,
    "noise": 0.25,
    "energy": 0.32
  },
  "actual_score": {
    "comfort_score": 0.86,
    "demand_satisfaction": 0.90,
    "coordination_score": 0.91,
    "action_quality": 0.86
  },
  "archive_summary": "卧室睡前闷热且潮湿时，低档新风 + 低档除湿 + 低风速空调优于开窗或高风量新风。",
  "confidence_update": 0.91
}
```

---

## 16. 实现建议

### 16.1 第一阶段

先实现规则评分系统：

```text
parameter_score
comfort_score
action_utility
hard_conflict_count
soft_conflict_cost
```

### 16.2 第二阶段

加入 discussion 和 memory 评价：

```text
activation_precision
activation_recall
memory_relevance
consensus_score
action_clarity
```

### 16.3 第三阶段

加入闭环学习：

```text
prediction_error
archive_quality
memory_reuse_rate
experience_confidence_change
```

---

## 17. 建议模块划分

可将评价系统拆成以下模块：

```text
evaluators/
  comfort_evaluator.py
  parameter_evaluator.py
  action_evaluator.py
  conflict_evaluator.py
  coordination_evaluator.py
  memory_evaluator.py
  archive_evaluator.py
```

每个模块职责：

| 模块 | 职责 |
|---|---|
| `comfort_evaluator.py` | 计算房间和系统整体舒适度 |
| `parameter_evaluator.py` | 计算单个环境变量得分 |
| `action_evaluator.py` | 计算每个 action 的 utility |
| `conflict_evaluator.py` | 检测硬冲突、软冲突、协同收益 |
| `coordination_evaluator.py` | 评价 agent 讨论和任务分配质量 |
| `memory_evaluator.py` | 评价知识图谱检索记忆质量 |
| `archive_evaluator.py` | 评价归档内容质量和可复用性 |

---

## 18. Codex 实现提示

可以要求 Codex 优先实现以下内容：

```text
请基于本文档实现一个智能家居多 agent 系统的评价模块。

第一版只需要实现：
1. parameter_score
2. comfort_score
3. action_utility
4. hard_conflict_count
5. soft_conflict_cost
6. synergy_bonus
7. prediction_error

请使用 Python dataclass 或 Pydantic 定义输入输出结构。
请保证所有评分结果归一化到 [0, 1]，惩罚项可单独返回。
请将不同 evaluator 拆成独立模块，方便后续扩展。
```
