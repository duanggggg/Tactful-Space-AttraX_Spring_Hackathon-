from __future__ import annotations

import asyncio
import copy
import json
import math
import random
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_event_id() -> str:
    return "evt_" + uuid.uuid4().hex[:12]


app = FastAPI(title="Sunroom Digital Twin Mock Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

RECENT_EVENTS: deque[dict[str, Any]] = deque(maxlen=200)
SUBSCRIBERS: set[asyncio.Queue] = set()
ACTIVE_SCENE = "manual"


LAYOUT: Dict[str, Any] = {
    "building": {
        "name": "北大小楼阳光房",
        "dimensions": {"length": 14.28, "width": 6.20, "platformHeight": 0.18},
        "platform": {"stepDepth": 0.42, "entryStepWidth": 2.85},
        "coreBox": {"center": [0.0, 1.45, -0.75], "size": [6.05, 2.90, 2.25]},
        "screen": {"center": [4.1, 1.85, -1.55], "size": [1.65, 0.92]},
        "meetingTable": {"center": [1.25, 0.76, 0.20], "size": [3.10, 0.08, 1.55]},
        "shelfWall": {"center": [-2.25, 1.20, -1.45], "size": [3.25, 2.35, 0.38]},
        "roof": {
            "main": {
                "profile": [[-3.05, 2.52], [0.00, 4.28], [3.00, 2.95]],
                "thickness": 0.10,
                "depth": 13.70,
                "position": [0.00, 0.00, 0.00],
            },
            "upper": {
                "profile": [[-1.25, 4.02], [0.65, 4.62], [2.65, 4.18]],
                "thickness": 0.08,
                "depth": 11.20,
                "position": [0.40, 0.00, -0.15],
            },
            "entry": {
                "profile": [[-3.35, 2.22], [-1.95, 2.95], [-0.55, 2.45]],
                "thickness": 0.08,
                "depth": 13.75,
                "position": [0.00, 0.00, 0.00],
            },
        },
        "braceXs": [-5.40, -3.20, -0.45, 2.20, 4.90],
        "deviceAnchors": {
            "light.perimeter": [0.00, 2.80, 0.00],
            "light.entry": [0.00, 2.45, 2.65],
            "screen.main": [4.10, 1.85, -1.55],
            "door.main": [0.00, 1.30, 3.02],
            "window.north": [-4.55, 2.40, -3.02],
            "curtain.front": [0.00, 1.55, 2.88],
            "ac.main": [-0.55, 2.45, -1.95],
            "freshair.main": [1.10, 2.30, -1.95],
            "robot.openclaw": [-5.85, 0.33, 2.75],
        },
    }
}


def seed_devices() -> Dict[str, Dict[str, Any]]:
    return {
        "light.perimeter": {
            "id": "light.perimeter",
            "name": "周边灯带",
            "domain": "lighting",
            "type": "light",
            "location": "roof.perimeter",
            "adapter_kind": "mock",
            "capabilities": ["set_on", "set_brightness", "set_cct", "scene"],
            "state": {"on": True, "brightness": 58, "cct": 4200, "scene": "idle"},
        },
        "light.entry": {
            "id": "light.entry",
            "name": "入口灯带",
            "domain": "lighting",
            "type": "light",
            "location": "entry.canopy",
            "adapter_kind": "mock",
            "capabilities": ["set_on", "set_brightness"],
            "state": {"on": False, "brightness": 0},
        },
        "screen.main": {
            "id": "screen.main",
            "name": "主显示屏",
            "domain": "display",
            "type": "screen",
            "location": "meeting.wall",
            "adapter_kind": "mock",
            "capabilities": ["power", "set_mode", "set_message"],
            "state": {"on": True, "mode": "dashboard", "message": "阳光房 Digital Twin 已连接"},
        },
        "door.main": {
            "id": "door.main",
            "name": "主入口门",
            "domain": "access",
            "type": "door",
            "location": "south.entry",
            "adapter_kind": "mock",
            "capabilities": ["open", "close", "lock", "unlock"],
            "state": {"position": 0, "moving": False, "locked": True},
        },
        "access.main": {
            "id": "access.main",
            "name": "门禁控制器",
            "domain": "access",
            "type": "access",
            "location": "south.entry",
            "adapter_kind": "mock",
            "capabilities": ["grant_user", "revoke_user", "get_access_logs"],
            "state": {"status": "idle", "last_user": None},
        },
        "window.north": {
            "id": "window.north",
            "name": "北侧开窗器",
            "domain": "environment",
            "type": "window",
            "location": "north.clerestory",
            "adapter_kind": "mock",
            "capabilities": ["open", "close", "stop", "set_auto_rule"],
            "state": {"position": 0, "moving": False, "auto_rule": "rain_safe"},
        },
        "curtain.front": {
            "id": "curtain.front",
            "name": "前侧窗帘",
            "domain": "environment",
            "type": "curtain",
            "location": "south.glass",
            "adapter_kind": "mock",
            "capabilities": ["open", "close", "scene", "get_position"],
            "state": {"position": 100, "scene": "open"},
        },
        "ac.main": {
            "id": "ac.main",
            "name": "壁挂空调控制器",
            "domain": "climate",
            "type": "ac",
            "location": "corebox.north",
            "adapter_kind": "mock",
            "capabilities": ["power", "set_mode", "set_temp", "set_fan", "read_state"],
            "state": {"power": True, "mode": "cool", "setpoint": 24, "fan_speed": "medium"},
        },
        "freshair.main": {
            "id": "freshair.main",
            "name": "新风机",
            "domain": "climate",
            "type": "freshair",
            "location": "corebox.north",
            "adapter_kind": "mock",
            "capabilities": ["set_mode", "set_fan_speed", "filter_life"],
            "state": {"power": True, "mode": "normal", "fan_speed": "low", "filter_life": 92},
        },
        "sensor.env": {
            "id": "sensor.env",
            "name": "环境传感器",
            "domain": "sensing",
            "type": "environment_sensor",
            "location": "meeting.center",
            "adapter_kind": "mock",
            "capabilities": ["read"],
            "state": {
                "temperature_c": 24.8,
                "humidity_pct": 47.0,
                "co2_ppm": 630,
                "lux": 520,
                "pm25": 16,
                "ts": now_iso(),
            },
        },
        "sensor.occupancy": {
            "id": "sensor.occupancy",
            "name": "占用传感器",
            "domain": "sensing",
            "type": "occupancy_sensor",
            "location": "meeting.center",
            "adapter_kind": "mock",
            "capabilities": ["read"],
            "state": {"count": 1, "occupied": True, "ts": now_iso()},
        },
        "sensor.rain": {
            "id": "sensor.rain",
            "name": "雨量传感器",
            "domain": "sensing",
            "type": "rain_sensor",
            "location": "outdoor.east",
            "adapter_kind": "mock",
            "capabilities": ["read"],
            "state": {"is_raining": False, "mmph": 0.0, "ts": now_iso()},
        },
        "robot.openclaw": {
            "id": "robot.openclaw",
            "name": "OpenClaw 机器人占位对象",
            "domain": "robot",
            "type": "robot",
            "location": "outdoor.entry.left",
            "adapter_kind": "mock",
            "capabilities": ["start_patrol", "dock", "stop"],
            "state": {"status": "docked", "progress": 0.0},
        },
    }


DEVICES = seed_devices()

AGENT_STATUSES = ["rest", "work"]
AGENT_COUNT = 3

AGENT_STATE: List[Dict[str, Any]] = []


def init_agent_state(count: int = AGENT_COUNT) -> List[Dict[str, Any]]:
    ts = now_iso()
    return [
        {
            "id": i + 1,
            "name": chr(ord("A") + i),
            "status": "rest",
            "ts": ts,
        }
        for i in range(count)
    ]


def get_mock_agent_statuses() -> List[Dict[str, Any]]:
    global AGENT_STATE

    if not AGENT_STATE:
        AGENT_STATE = init_agent_state()

    return [
        {
            "id": agent["id"],
            "name": agent["name"],
            "status": agent["status"],
            "ts": agent["ts"],
        }
        for agent in AGENT_STATE
    ]

def scene_specs() -> List[Dict[str, Any]]:
    return [
        {
            "id": "welcome",
            "name": "欢迎模式",
            "description": "入口灯光与欢迎屏联动",
            "commands": [
                {"device_id": "light.entry", "action": "set_on", "params": {"on": True}},
                {"device_id": "light.entry", "action": "set_brightness", "params": {"brightness": 80}},
                {"device_id": "screen.main", "action": "set_mode", "params": {"mode": "welcome"}},
                {"device_id": "screen.main", "action": "set_message", "params": {"message": "欢迎来到阳光房 OpenClaw"}},
                {"device_id": "light.perimeter", "action": "set_brightness", "params": {"brightness": 62}},
            ],
        },
        {
            "id": "presentation",
            "name": "汇报模式",
            "description": "更适合会议和展示",
            "commands": [
                {"device_id": "curtain.front", "action": "close", "params": {"position": 45}},
                {"device_id": "light.perimeter", "action": "set_on", "params": {"on": True}},
                {"device_id": "light.perimeter", "action": "set_brightness", "params": {"brightness": 65}},
                {"device_id": "light.perimeter", "action": "set_cct", "params": {"cct": 4200}},
                {"device_id": "screen.main", "action": "set_mode", "params": {"mode": "presentation"}},
                {"device_id": "screen.main", "action": "set_message", "params": {"message": "汇报模式已就绪"}},
            ],
        },
        {
            "id": "focus",
            "name": "专注模式",
            "description": "适合研究与小范围讨论",
            "commands": [
                {"device_id": "light.entry", "action": "set_on", "params": {"on": False}},
                {"device_id": "light.perimeter", "action": "set_brightness", "params": {"brightness": 48}},
                {"device_id": "screen.main", "action": "set_mode", "params": {"mode": "focus"}},
                {"device_id": "screen.main", "action": "set_message", "params": {"message": "专注模式"}},
            ],
        },
        {
            "id": "ventilation",
            "name": "通风模式",
            "description": "开窗与新风联动",
            "commands": [
                {"device_id": "window.north", "action": "open", "params": {"position": 60}},
                {"device_id": "freshair.main", "action": "set_mode", "params": {"mode": "ventilate"}},
                {"device_id": "freshair.main", "action": "set_fan_speed", "params": {"fan_speed": "high"}},
                {"device_id": "ac.main", "action": "power", "params": {"on": False}},
            ],
        },
        {
            "id": "night",
            "name": "夜间模式",
            "description": "低功耗与安全状态",
            "commands": [
                {"device_id": "light.entry", "action": "set_on", "params": {"on": False}},
                {"device_id": "light.perimeter", "action": "set_brightness", "params": {"brightness": 8}},
                {"device_id": "screen.main", "action": "power", "params": {"on": False}},
                {"device_id": "curtain.front", "action": "close", "params": {"position": 0}},
                {"device_id": "door.main", "action": "lock", "params": {}},
            ],
        },
    ]


SCENES = scene_specs()


class CommandRequest(BaseModel):
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    source: str = "api"
    task_id: Optional[str] = None
    trace_id: Optional[str] = None


class SceneRequest(BaseModel):
    scene: str
    source: str = "api"
    task_id: Optional[str] = None
    trace_id: Optional[str] = None


class OfficeEventRequest(BaseModel):
    type: str
    zone: str
    status: str
    message: str
    agent_id: str = "openclaw-main"
    task_id: Optional[str] = None
    trace_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


class AgentAssignmentRequest(BaseModel):
    agent_ids: List[int] = Field(default_factory=list)
    status: str = "rest"
    duration_seconds: int = 0
    source: str = "main_chat"
    task_id: Optional[str] = None
    trace_id: Optional[str] = None




CommandRequest.model_rebuild()
SceneRequest.model_rebuild()
OfficeEventRequest.model_rebuild()
AgentAssignmentRequest.model_rebuild()


async def publish_event(event: Dict[str, Any]) -> None:
    payload = {
        "event_id": make_event_id(),
        "ts": now_iso(),
        **event,
    }
    RECENT_EVENTS.append(payload)
    dead: List[asyncio.Queue] = []
    for queue in list(SUBSCRIBERS):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(queue)
    for queue in dead:
        SUBSCRIBERS.discard(queue)


def clone_device(device_id: str) -> Dict[str, Any]:
    return copy.deepcopy(DEVICES[device_id])


def list_devices_payload() -> Dict[str, Any]:
    return {
        "items": [copy.deepcopy(DEVICES[key]) for key in sorted(DEVICES)],
        "active_scene": ACTIVE_SCENE,
    }


def get_device_or_404(device_id: str) -> Dict[str, Any]:
    device = DEVICES.get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail=f"Unknown device: {device_id}")
    return device


def coerce_percent(value: Any, default: int) -> int:
    try:
        number = int(value)
    except Exception:
        number = default
    return max(0, min(100, number))


async def apply_command(
    device_id: str,
    action: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    source: str,
    task_id: Optional[str] = None,
    trace_id: Optional[str] = None,
    publish: bool = True,
) -> Dict[str, Any]:
    params = params or {}
    device = get_device_or_404(device_id)
    state = device["state"]

    if device_id.startswith("light."):
        if action == "set_on":
            state["on"] = bool(params.get("on", True))
            if not state["on"]:
                state["brightness"] = 0
        elif action == "set_brightness":
            state["brightness"] = coerce_percent(params.get("brightness"), state.get("brightness", 0))
            state["on"] = state["brightness"] > 0
        elif action == "set_cct":
            state["cct"] = int(params.get("cct", state.get("cct", 4000)))
        elif action == "scene":
            state["scene"] = str(params.get("scene", "manual"))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action for {device_id}: {action}")

    elif device_id == "screen.main":
        if action == "power":
            state["on"] = bool(params.get("on", True))
        elif action == "set_mode":
            state["mode"] = str(params.get("mode", "dashboard"))
            state["on"] = True
        elif action == "set_message":
            state["message"] = str(params.get("message", ""))
            state["on"] = True
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action for {device_id}: {action}")

    elif device_id == "door.main":
        if action == "open":
            state["position"] = coerce_percent(params.get("position", 100), 100)
            state["moving"] = False
        elif action == "close":
            state["position"] = 0
            state["moving"] = False
        elif action == "lock":
            state["locked"] = True
        elif action == "unlock":
            state["locked"] = False
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action for {device_id}: {action}")

    elif device_id == "access.main":
        if action == "grant_user":
            state["status"] = "granted"
            state["last_user"] = params.get("user", "visitor")
        elif action == "revoke_user":
            state["status"] = "revoked"
            state["last_user"] = params.get("user", state.get("last_user"))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action for {device_id}: {action}")

    elif device_id == "window.north":
        if action == "open":
            state["position"] = coerce_percent(params.get("position", 100), 100)
            state["moving"] = False
        elif action == "close":
            state["position"] = 0
            state["moving"] = False
        elif action == "stop":
            state["moving"] = False
        elif action == "set_auto_rule":
            state["auto_rule"] = str(params.get("auto_rule", "manual"))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action for {device_id}: {action}")

    elif device_id == "curtain.front":
        if action == "open":
            state["position"] = coerce_percent(params.get("position", 100), 100)
            state["scene"] = "open"
        elif action == "close":
            state["position"] = coerce_percent(params.get("position", 0), 0)
            state["scene"] = "closed"
        elif action == "scene":
            scene_name = str(params.get("scene", "manual"))
            state["scene"] = scene_name
            if scene_name == "presentation":
                state["position"] = 45
            elif scene_name == "open":
                state["position"] = 100
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action for {device_id}: {action}")

    elif device_id == "ac.main":
        if action == "power":
            state["power"] = bool(params.get("on", True))
        elif action == "set_mode":
            state["mode"] = str(params.get("mode", state.get("mode", "cool")))
            state["power"] = True
        elif action == "set_temp":
            state["setpoint"] = float(params.get("temp", params.get("setpoint", state.get("setpoint", 24))))
            state["power"] = True
        elif action == "set_fan":
            state["fan_speed"] = str(params.get("speed", params.get("fan_speed", "medium")))
            state["power"] = True
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action for {device_id}: {action}")

    elif device_id == "freshair.main":
        if action == "set_mode":
            state["mode"] = str(params.get("mode", "normal"))
            state["power"] = True
        elif action == "set_fan_speed":
            state["fan_speed"] = str(params.get("fan_speed", "low"))
            state["power"] = True
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action for {device_id}: {action}")

    elif device_id == "robot.openclaw":
        if action == "start_patrol":
            state["status"] = "running"
        elif action == "dock":
            state["status"] = "docked"
            state["progress"] = 0.0
        elif action == "stop":
            state["status"] = "idle"
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported action for {device_id}: {action}")

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported device: {device_id}")

    if publish:
        await publish_event(
            {
                "type": "device.command_applied",
                "source": source,
                "task_id": task_id,
                "trace_id": trace_id,
                "device_id": device_id,
                "action": action,
                "params": params,
                "device_state": copy.deepcopy(state),
            }
        )

    return clone_device(device_id)


def compute_telemetry() -> Dict[str, Any]:
    env = DEVICES["sensor.env"]["state"]
    occ = DEVICES["sensor.occupancy"]["state"]
    rain = DEVICES["sensor.rain"]["state"]
    light = DEVICES["light.perimeter"]["state"]
    entry = DEVICES["light.entry"]["state"]
    ac = DEVICES["ac.main"]["state"]
    fresh = DEVICES["freshair.main"]["state"]
    window = DEVICES["window.north"]["state"]
    screen = DEVICES["screen.main"]["state"]
    robot = DEVICES["robot.openclaw"]["state"]

    estimated_watts = (
        light.get("brightness", 0) * 5
        + entry.get("brightness", 0) * 2
        + (800 if screen.get("on") else 0)
        + (620 if ac.get("power") else 0)
        + (220 if fresh.get("power") else 0)
        + (90 if robot.get("status") == "running" else 10)
    )

    return {
        "updated_at": now_iso(),
        "scene": ACTIVE_SCENE,
        "environment": copy.deepcopy(env),
        "occupancy": copy.deepcopy(occ),
        "weather": copy.deepcopy(rain),
        "power": {"estimated_watts": int(estimated_watts)},
        "comfort": {
            "window_position": window["position"],
            "curtain_position": DEVICES["curtain.front"]["state"]["position"],
            "ac_mode": ac["mode"],
            "freshair_mode": fresh["mode"],
        },
    }


async def sensor_loop() -> None:
    rain_flip_counter = 0
    try:
        while True:
            await asyncio.sleep(3)
            env = DEVICES["sensor.env"]["state"]
            occ = DEVICES["sensor.occupancy"]["state"]
            rain = DEVICES["sensor.rain"]["state"]
            ac = DEVICES["ac.main"]["state"]
            fresh = DEVICES["freshair.main"]["state"]
            window = DEVICES["window.north"]["state"]
            robot = DEVICES["robot.openclaw"]["state"]

            rain_flip_counter += 1
            if rain_flip_counter % 6 == 0 and random.random() < 0.28:
                rain["is_raining"] = not rain["is_raining"]
                rain["mmph"] = round(random.uniform(0.8, 5.6), 1) if rain["is_raining"] else 0.0
                rain["ts"] = now_iso()
                await publish_event(
                    {
                        "type": "sensor.rain_changed",
                        "source": "system.sensor_loop",
                        "device_id": "sensor.rain",
                        "device_state": copy.deepcopy(rain),
                    }
                )

            # climate drift
            ventilation_factor = window["position"] / 100.0 + (0.35 if fresh["mode"] == "ventilate" else 0.0)
            cooling_factor = 0.45 if ac["power"] and ac["mode"] == "cool" else 0.0
            heating_factor = 0.30 if ac["power"] and ac["mode"] == "heat" else 0.0

            target_temp = 25.8 - cooling_factor * 4 + heating_factor * 4 - ventilation_factor * 1.2
            env["temperature_c"] = round(env["temperature_c"] + (target_temp - env["temperature_c"]) * 0.18 + random.uniform(-0.12, 0.12), 1)

            target_co2 = 930 - ventilation_factor * 420 - (30 if occ["count"] == 0 else 0)
            env["co2_ppm"] = int(max(420, min(1200, env["co2_ppm"] + (target_co2 - env["co2_ppm"]) * 0.20 + random.uniform(-18, 18))))

            env["humidity_pct"] = round(max(30, min(78, env["humidity_pct"] + random.uniform(-1.0, 1.0) - ventilation_factor * 0.4)), 1)

            light_level = DEVICES["light.perimeter"]["state"]["brightness"] * 5 + DEVICES["light.entry"]["state"]["brightness"] * 2
            curtain_factor = DEVICES["curtain.front"]["state"]["position"] / 100.0
            daylight = 220 if not rain["is_raining"] else 90
            env["lux"] = int(max(30, min(1600, daylight * curtain_factor + light_level + random.uniform(-15, 15))))
            env["pm25"] = int(max(5, min(60, env["pm25"] + random.uniform(-2.0, 2.0) - (0.5 if fresh["mode"] == "ventilate" else 0))))

            env["ts"] = now_iso()

            # occupancy and robot
            if ACTIVE_SCENE in {"presentation", "focus"}:
                occ["count"] = 2
                occ["occupied"] = True
            elif ACTIVE_SCENE == "night":
                occ["count"] = 0
                occ["occupied"] = False
            else:
                if random.random() < 0.15:
                    occ["count"] = random.choice([0, 1, 2, 3])
                    occ["occupied"] = occ["count"] > 0
            occ["ts"] = now_iso()

            if robot["status"] == "running":
                robot["progress"] = (robot["progress"] + 0.11) % 1.0
            elif robot["status"] == "docked":
                robot["progress"] = 0.0

            # rain-safe automation
            if rain["is_raining"] and window["position"] > 0 and window.get("auto_rule") == "rain_safe":
                await apply_command(
                    "window.north",
                    "close",
                    {},
                    source="rule.rain_safe",
                    task_id=None,
                    trace_id=None,
                    publish=True,
                )
                await publish_event(
                    {
                        "type": "automation.applied",
                        "source": "rule.rain_safe",
                        "message": "检测到降雨，自动执行关窗",
                        "device_id": "window.north",
                        "device_state": copy.deepcopy(DEVICES["window.north"]["state"]),
                    }
                )
    except asyncio.CancelledError:
        pass

@app.on_event("startup")
async def startup() -> None:
    app.state.sensor_task = asyncio.create_task(sensor_loop())
    await publish_event({"type": "system.started", "source": "mock_backend", "message": "Digital twin mock backend started"})



@app.on_event("shutdown")
async def shutdown() -> None:
    task = getattr(app.state, "sensor_task", None)
    if task:
        task.cancel()


@app.get("/api/v1/health")
async def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "service": "sunroom-digital-twin",
        "mode": "mock",
        "active_scene": ACTIVE_SCENE,
        "time": now_iso(),
    }


@app.get("/api/v1/layout")
async def layout() -> Dict[str, Any]:
    return copy.deepcopy(LAYOUT)


@app.get("/api/v1/devices")
async def list_devices() -> Dict[str, Any]:
    return list_devices_payload()


@app.get("/api/v1/devices/{device_id}")
async def get_device(device_id: str) -> Dict[str, Any]:
    return clone_device(device_id)


@app.post("/api/v1/devices/{device_id}/commands")
async def command_device(device_id: str, body: CommandRequest) -> Dict[str, Any]:
    device = await apply_command(
        device_id,
        body.action,
        body.params,
        source=body.source,
        task_id=body.task_id,
        trace_id=body.trace_id,
        publish=True,
    )
    return {"ok": True, "device": device, "active_scene": ACTIVE_SCENE}


@app.get("/api/v1/scenes")
async def list_scenes() -> Dict[str, Any]:
    return {"items": copy.deepcopy(SCENES), "active_scene": ACTIVE_SCENE}


@app.post("/api/v1/scenes/activate")
async def activate_scene(body: SceneRequest) -> Dict[str, Any]:
    global ACTIVE_SCENE
    scene = next((item for item in SCENES if item["id"] == body.scene), None)
    if not scene:
        raise HTTPException(status_code=404, detail=f"Unknown scene: {body.scene}")

    for step in scene["commands"]:
        await apply_command(
            step["device_id"],
            step["action"],
            step.get("params", {}),
            source=body.source,
            task_id=body.task_id,
            trace_id=body.trace_id,
            publish=True,
        )
    ACTIVE_SCENE = scene["id"]
    await publish_event(
        {
            "type": "scene.activated",
            "source": body.source,
            "task_id": body.task_id,
            "trace_id": body.trace_id,
            "scene": scene["id"],
            "scene_name": scene["name"],
        }
    )
    return {"ok": True, "scene": scene["id"], "active_scene": ACTIVE_SCENE}


@app.get("/api/v1/telemetry")
async def telemetry() -> Dict[str, Any]:
    return compute_telemetry()

@app.get("/api/v1/agents/status")
async def agents_status() -> List[Dict[str, Any]]:
    return get_mock_agent_statuses()


@app.post("/api/v1/agents/assign")
async def assign_agents(body: AgentAssignmentRequest) -> Dict[str, Any]:
    global AGENT_STATE

    if body.status not in AGENT_STATUSES:
        raise HTTPException(status_code=400, detail=f"invalid status: {body.status}")

    if not AGENT_STATE:
        AGENT_STATE = init_agent_state()

    known_ids = {int(agent["id"]) for agent in AGENT_STATE}
    valid_ids = sorted({int(agent_id) for agent_id in body.agent_ids if int(agent_id) in known_ids})
    if not valid_ids:
        raise HTTPException(status_code=400, detail="no valid agent ids")

    ts = now_iso()
    for agent in AGENT_STATE:
        if int(agent["id"]) in valid_ids:
            agent["status"] = body.status
            agent["ts"] = ts

    await publish_event(
        {
            "type": "agents.assigned",
            "source": body.source,
            "status": body.status,
            "message": f"agents {valid_ids} set to {body.status}",
            "payload": {
                "agent_ids": valid_ids,
                "duration_seconds": int(body.duration_seconds),
                "persistent": True,
                "task_id": body.task_id,
                "trace_id": body.trace_id,
            },
        }
    )
    return {
        "ok": True,
        "agent_ids": valid_ids,
        "status": body.status,
        "duration_seconds": int(body.duration_seconds),
        "persistent": True,
    }

@app.get("/api/v1/events/recent")
async def recent_events() -> Dict[str, Any]:
    return {"items": list(RECENT_EVENTS)}


@app.get("/api/v1/events/stream")
async def events_stream() -> StreamingResponse:
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        SUBSCRIBERS.add(queue)
        await queue.put({"type": "hello", "source": "mock_backend", "message": "sse connected"})
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            SUBSCRIBERS.discard(queue)

    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }
    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=headers)


@app.post("/api/v1/office-ui/events")
async def office_ui_events(body: OfficeEventRequest) -> Dict[str, Any]:
    await publish_event(
        {
            "type": body.type,
            "source": "office_ui.bridge",
            "zone": body.zone,
            "status": body.status,
            "message": body.message,
            "agent_id": body.agent_id,
            "task_id": body.task_id,
            "trace_id": body.trace_id,
            "payload": body.payload,
        }
    )
    return {"ok": True}
