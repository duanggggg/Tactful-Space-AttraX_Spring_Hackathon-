# 阳光房 OpenClaw Digital Twins

本目录是一个独立的阳光房 `digital twins` 子工程，依据以下文档整理：

- `backend/vis/docs/digital_twin_prd.md`
- `backend/vis/docs/digital_twin_tad.md`
- `backend/vis/docs/three_fiber_code.zip`
- `backend/vis/docs/digital_twin_skills.zip`

实现目标：

- 提供可独立启动的 `FastAPI mock backend`
- 提供可独立启动的 `React + Vite + React Three Fiber` 前端
- 提供可直接被 OpenClaw 调用的 Python 脚本
- 不修改主项目其他目录

## 目录说明

- `mock_backend/`：阳光房 digital twins mock backend
- `frontend/`：阳光房 3D 前端
- `scripts/`：可被 OpenClaw/skill 调用的最小脚本
- `references/`：接口契约与设备 taxonomy 参考
- `digital_twins_wait_outside_to_modify_code.md`：若未来要接入主工程，先审阅这个文件

## 启动方式

### 1. 启动 backend

```powershell
cd backend/vis/docs/digital_twins/mock_backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn app:app --reload --port 8787
```

### 2. 启动 frontend

```powershell
cd backend/vis/docs/digital_twins/frontend
npm install
npm run dev
```

默认访问地址：

- backend: `http://127.0.0.1:8787`
- frontend: `http://127.0.0.1:5173`

## 脚本示例

读取状态：

```powershell
cd backend/vis/docs/digital_twins/scripts
python get_state.py --layout
```

下发设备命令：

```powershell
python device_command.py --device light.perimeter --action set_brightness --params "{\"brightness\":70}"
```

切换场景：

```powershell
python scene_activate.py --scene presentation
```

推送 Office UI 事件：

```powershell
python publish_event.py --type avatar.say --zone execution --status executing --message "正在切换到汇报模式"
```

检测机器人链路：

```powershell
python check_robot_link.py --agent-base-url http://127.0.0.1:8003 --twin-base-url http://127.0.0.1:8787
```

这条检查会依次验证：

- `agent backend` 是否可访问，并输出 `/api/agent/health`
- `digital twin backend` 是否可访问，并输出 `/api/v1/health`
- `backend -> twin bridge` 是否能把事件写入 `recent events`
- agent 状态是否能从 `rest` 切到 `work`，再切回 `rest`

如果最后 `summary.ok = true`，说明当前代码链路已经打通；如果 `agent_health.config.has_api_key = false`，则表示桥接通了，但真实模型回复链路还没有完整可用。

## 说明

当前版本故意保持为“独立子工程”，这样能在不动现有管道项目的情况下先把阳光房 OpenClaw 跑起来。

如果后续确认要挂入主工程，请先看：

- `backend/vis/docs/digital_twins/digital_twins_wait_outside_to_modify_code.md`
