# 房屋设备 MCP 完整方案

## 1. 目标

当前 `mcp/` 目录负责把机器人语音文本接入本地 MCP 链路，并把房屋内三类设备统一纳入识别和执行：

- 电脑
- 灯光
- 空调

原则是：

1. 只要对话涉及这三类设备的功能，就进入 `classify_devices` -> `device_llm_server.py`。
2. `device_llm_server.py` 必须同时输出“识别结果 + 每个家电的执行方案”。
3. 执行方案要同步到 digital twin 后端，保证设备状态和 agent 状态一起变化。

## 2. 设备映射

### 电脑

- 用户意图关键词：
  - 电脑、显示器、显示屏、屏幕、投屏、汇报、演示、会议屏、专注
- Digital Twin 设备：
  - `screen.main`
- 对应 agent：
  - `agent 3`
- 典型动作：
  - 打开电脑：`power -> on`
  - 汇报模式：`set_mode -> presentation`，并更新提示文案
  - 专注模式：`set_mode -> focus`
  - 关闭电脑：`power -> off`

### 灯光

- 用户意图关键词：
  - 灯、灯光、照明、亮度、调亮、调暗、开灯、关灯
- Digital Twin 设备：
  - `light.perimeter`
  - `light.entry`
- 对应 agent：
  - `agent 2`
- 典型动作：
  - 开灯：提高两组灯的亮度
  - 调亮：提高亮度到更高档位
  - 调暗：降低亮度
  - 关灯：两组灯关闭

### 空调

- 用户意图关键词：
  - 空调、冷气、制冷、制热、温度、降温、升温、太热、太冷
- Digital Twin 设备：
  - `ac.main`
- 对应 agent：
  - `agent 1`
- 典型动作：
  - 打开空调：`power -> on`
  - 制冷：`set_mode -> cool`，默认 24℃
  - 制热：`set_mode -> heat`，默认 26℃
  - 调温：`set_temp`
  - 关闭空调：`power -> off`

## 3. Agent 联动规则

- agent 1 对应空调
- agent 2 对应灯光
- agent 3 对应电脑

状态规则：

- 初始化全部为 `rest`
- 当且仅当机器人指令触发对应设备执行时，相关 agent 变为 `work`
- 当机器人明确要求关闭某设备时，对应 agent 变为 `rest`
- 与本次指令无关的 agent，不强制重置

## 4. 前后端联动链路

完整链路如下：

1. 机器人文本进入 MCP
2. `llm_agent.py` 调用 `classify_devices`
3. `device_llm_server.py` 调用本地/外部兼容 OpenAI 的大模型
4. `device_llm_server.py` 生成三类设备的执行方案
5. `device_llm_server.py` 调用 digital twin 后端：
   - `/api/v1/devices/{device_id}/commands`
   - `/api/v1/agents/assign`
6. digital twin mock backend 通过 SSE 和轮询把状态推给前端
7. 前端可视化同步更新：
   - 屏幕/灯光/空调模型状态
   - 3 个 agent 的工作/休息状态

## 5. 当前文件职责

- `mcp/llm_agent.py`
  - MCP 对外工具入口
- `mcp/device_llm_server.py`
  - 三类设备统一识别、动作规划、digital twin 同步
- `backend/vis/digital_twins/mock_backend/app.py`
  - 接收设备命令和 agent 状态更新
- `backend/vis/digital_twins/frontend/src`
  - 设备与 agent 的可视化展示

## 6. 推荐测试语句

- `打开房屋里的电脑`
- `把灯光调亮一点`
- `空调调到24度`
- `打开电脑，进入汇报模式`
- `关闭空调和灯`
- `请把电脑打开、灯调亮、空调调到24度`

## 7. 启动目录

MCP 目录已经统一为：

```bash
/Users/fengdefan/Documents/GitHub/homellm/mcp
```
