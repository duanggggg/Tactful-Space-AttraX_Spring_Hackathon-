# Attrax 智能家居中枢项目蓝图

## 1. 项目定位

本项目面向 Attrax 黑客松赛道二“硬件、具身”，目标是在 24 小时内完成一个可演示的智能家居中枢 MVP：用户通过语音或屏幕聊天输入自然语言需求，系统将需求解析为设备动作，控制空调、灯光、窗帘等家庭设备，并把执行状态实时反馈到展示屏。

核心叙事是：AI 不只是聊天助手，而是家庭空间的中枢。它能理解人的意图，感知环境状态，唤醒硬件执行动作，并在屏幕上把“家正在回应你”可视化出来。

## 2. MVP 范围

本轮只做最能打动评委的闭环：

- 聊天控制：用户输入“把空调调到 23 度”“灯光调到 30%”“窗帘打开一半”“进入观影模式”。
- 设备控制：后端把自然语言解析为结构化命令，并更新空调、灯光、窗帘和环境传感器状态。
- 实时反馈：前端通过 SSE 接收后端事件，展示聊天回复、设备卡片、事件时间线和 3D 房屋状态变化。
- 智能建议：规则引擎根据温度、光照、窗帘位置给出建议，例如室温偏高时建议降温。
- 演示兜底：物理硬件暂不作为硬依赖，默认使用 mock/simulator；真实设备后续通过 adapter 替换。

## 3. 系统架构

### 前端

新版展示必须以 `frontend/screen-display/house-detail.js` 为核心，不另起 mock 页面。主入口为：

- `house-detail.html`
- `house-detail.js`

页面结构：

- 左侧：聊天面板和四个快速演示指令。
- 中间：Three.js 3D 房屋展示，加载现有房屋 GLB，失败时使用简化房屋兜底。
- 右侧：设备状态卡片、滑块控制、智能建议。
- 底部：实时事件时间线和 reset 按钮。

3D 状态映射：

- 灯光亮度 -> 室内点光源强度和发光球体。
- 空调温度/开关 -> 空调机身与冷气流可视化。
- 窗帘开合 -> 两侧窗帘模型位置和宽度变化。
- 环境状态 -> 房屋屏幕上的实时温度、光照、设备摘要。

### 后端

新增后端模块：

- `backend/attrax_home.py`

挂载在主 FastAPI：

- `GET /api/attrax/home/state`
- `POST /api/attrax/home/chat`
- `POST /api/attrax/home/devices/{device_id}/commands`
- `GET /api/attrax/home/events/stream`
- `POST /api/attrax/home/reset`
- `POST /api/attrax/home/scene`

核心设备：

- `ac.main`：客厅空调，支持开关、设温、模式、风速。
- `light.living`：客厅主灯，支持开关、亮度、色温。
- `curtain.living`：客厅窗帘，支持打开、关闭、指定开合比例。
- `sensor.env`：环境传感器，提供温度、湿度、光照、CO2、占用状态。

自然语言解析先采用规则策略，保证比赛演示稳定。后续可以把规则解析替换为 LLM function calling 或多智能体规划。

## 4. API 数据流

用户聊天链路：

1. 前端向 `POST /api/attrax/home/chat` 发送 `{ message, session_id }`。
2. 后端发布 `chat.user_message` 事件。
3. 后端规则解析得到动作数组，发布 `intent.parsed` 事件。
4. 后端执行设备命令，发布 `device.command_applied` 事件。
5. 后端刷新智能建议，发布 `automation.suggestion` 事件。
6. 前端 SSE 收到事件后更新设备卡片、3D 场景、时间线和建议区。

直接控制链路：

1. 用户拖动设备卡片滑块。
2. 前端向 `POST /api/attrax/home/devices/{device_id}/commands` 发送结构化命令。
3. 后端更新状态并推送 `device.command_applied`。
4. 前端实时同步。

演示恢复链路：

1. 用户点击“重置演示”。
2. 前端调用 `POST /api/attrax/home/reset`。
3. 后端恢复固定初始状态，便于现场反复演示。

## 5. 核心 Demo Case

比赛现场优先演示以下 4 个稳定场景：

1. “把空调调到 23 度”：展示自然语言解析、空调设温、室温逐步趋近、3D 冷气流变化。
2. “灯光调到 30%”：展示灯光亮度卡片、室内光源和 3D 发光强度同步变化。
3. “窗帘打开一半”：展示窗帘百分比、3D 窗帘位置和光照 lux 变化。
4. “进入观影模式”：联动灯光变暗、窗帘收合、空调调整到舒适温度，体现智能场景编排。

## 6. 后续硬件接入方式

当前 mock 状态层可以替换为真实硬件 adapter，前端和 API 不需要重写：

- 空调 adapter：对接红外网关、米家、Home Assistant 或厂商 API。
- 灯光 adapter：对接智能灯泡、继电器或 Zigbee 网关。
- 窗帘 adapter：对接电机控制器或 Home Assistant cover entity。
- 传感器 adapter：对接温湿度、光照、人体存在传感器。

建议保持统一命令模型：先读状态、再写命令、再读回验证、最后推送事件。

## 7. 运行方式

启动后端：

```powershell
cd backend
python main.py
```

访问前端：

```text
http://127.0.0.1:8003/attrax-display/house-detail.html
```

如果单独用静态服务器打开 `frontend/screen-display/house-detail.html`，前端会默认请求：

```text
http://127.0.0.1:8003/api/attrax/home
```

也可以通过 query 参数指定 API：

```text
house-detail.html?api=http://127.0.0.1:8003
```

## 8. 验收标准

- 四个核心 demo case 都能跑通。
- 聊天回复、右侧设备卡片、3D 场景、底部事件时间线状态一致。
- SSE 断开时前端可以降级轮询。
- 后端 reset 后可以重复演示。
- 即使物理硬件不可用，也能完整展示智能家居中枢闭环。
