# API Contract

## Contents
- base url and authentication
- key endpoints
- command envelope
- event expectations
- read-write-verify pattern

## Base URL
通过环境变量 `SUNROOM_TWIN_BASE_URL` 指定，默认 `http://127.0.0.1:8787`。

## Key Endpoints
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

## Command Envelope
```json
{
  "action": "set_brightness",
  "params": { "brightness": 70 },
  "source": "skill.sunroom-digital-twin-core",
  "task_id": "optional",
  "trace_id": "optional"
}
```

## Event Expectations
执行成功后，backend 应产生至少一条含 `device_id` 与 `device_state` 的事件。  
前端和 office_ui 都消费同一条事件。

## Read-Write-Verify
推荐固定顺序：
1. read current state
2. write command
3. read back state
4. if needed, publish office_ui event
