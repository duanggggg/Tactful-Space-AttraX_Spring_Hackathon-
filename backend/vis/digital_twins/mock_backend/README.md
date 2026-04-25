# mock_backend

## 启动
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload --port 8787
```

## 关键接口
- `GET /api/v1/health`
- `GET /api/v1/layout`
- `GET /api/v1/devices`
- `GET /api/v1/devices/{device_id}`
- `POST /api/v1/devices/{device_id}/commands`
- `GET /api/v1/scenes`
- `POST /api/v1/scenes/activate`
- `GET /api/v1/telemetry`
- `GET /api/v1/events/recent`
- `GET /api/v1/events/stream`
- `POST /api/v1/office-ui/events`

## 说明
这是一个 mock twin backend：
- 用内存状态模拟设备
- 会周期性更新环境 telemetry
- 会在下雨时自动触发关窗规则
- 事件会通过 SSE 推送给前端
