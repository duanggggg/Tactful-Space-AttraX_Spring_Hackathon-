from __future__ import annotations

import asyncio
import copy
import json
import re
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field


router = APIRouter(prefix="/api/attrax/home", tags=["attrax-home"])

RECENT_EVENTS: deque[dict[str, Any]] = deque(maxlen=80)
SUBSCRIBERS: set[asyncio.Queue] = set()


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def event_id() -> str:
    return "attrax_evt_" + uuid.uuid4().hex[:10]


def seed_devices() -> Dict[str, Dict[str, Any]]:
    ts = now_iso()
    return {
        "ac.main": {
            "id": "ac.main",
            "name": "客厅空调",
            "domain": "climate",
            "type": "ac",
            "location": "living_room",
            "capabilities": ["power", "set_temp", "set_mode", "set_fan"],
            "state": {"power": True, "mode": "cool", "setpoint": 24, "fan_speed": "auto"},
        },
        "light.living": {
            "id": "light.living",
            "name": "客厅主灯",
            "domain": "lighting",
            "type": "light",
            "location": "living_room",
            "capabilities": ["set_on", "set_brightness", "set_cct"],
            "state": {"on": True, "brightness": 72, "cct": 4200},
        },
        "curtain.living": {
            "id": "curtain.living",
            "name": "客厅窗帘",
            "domain": "cover",
            "type": "curtain",
            "location": "living_room_window",
            "capabilities": ["open", "close", "set_position"],
            "state": {"position": 80, "moving": False},
        },
        "sensor.env": {
            "id": "sensor.env",
            "name": "环境传感器",
            "domain": "sensing",
            "type": "environment_sensor",
            "location": "living_room",
            "capabilities": ["read"],
            "state": {
                "temperature_c": 27.2,
                "humidity_pct": 48,
                "lux": 360,
                "co2_ppm": 620,
                "occupied": True,
                "ts": ts,
            },
        },
    }


DEVICES = seed_devices()
ACTIVE_SCENE = "manual"
LAST_REPLY = "智能家居中枢已就绪。"


class CommandRequest(BaseModel):
    action: str
    params: Dict[str, Any] = Field(default_factory=dict)
    source: str = "ui"
    trace_id: Optional[str] = None


class ChatRequest(BaseModel):
    message: str
    session_id: str = "attrax-demo"


class SceneRequest(BaseModel):
    scene: str
    source: str = "ui"


def clone_state() -> Dict[str, Any]:
    return {
        "devices": [copy.deepcopy(DEVICES[key]) for key in sorted(DEVICES)],
        "environment": copy.deepcopy(DEVICES["sensor.env"]["state"]),
        "active_scene": ACTIVE_SCENE,
        "suggestions": compute_suggestions(),
        "recent_events": list(RECENT_EVENTS),
        "last_reply": LAST_REPLY,
        "updated_at": now_iso(),
    }


async def publish_event(event: Dict[str, Any]) -> None:
    payload = {"id": event_id(), "ts": now_iso(), **event}
    RECENT_EVENTS.appendleft(payload)
    dead: List[asyncio.Queue] = []
    for queue in list(SUBSCRIBERS):
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            dead.append(queue)
    for queue in dead:
        SUBSCRIBERS.discard(queue)


def coerce_percent(value: Any, default: int = 0) -> int:
    try:
        number = int(float(value))
    except Exception:
        number = default
    return max(0, min(100, number))


def coerce_temp(value: Any, default: float = 24) -> float:
    try:
        number = float(value)
    except Exception:
        number = default
    return max(16, min(30, round(number, 1)))


def get_device(device_id: str) -> Dict[str, Any]:
    if device_id not in DEVICES:
        raise HTTPException(status_code=404, detail=f"unknown device: {device_id}")
    return DEVICES[device_id]


def update_environment_after_command(device_id: str) -> None:
    env = DEVICES["sensor.env"]["state"]
    ac = DEVICES["ac.main"]["state"]
    light = DEVICES["light.living"]["state"]
    curtain = DEVICES["curtain.living"]["state"]

    if device_id == "ac.main" and ac.get("power"):
        setpoint = float(ac.get("setpoint", 24))
        env["temperature_c"] = round(float(env["temperature_c"]) + (setpoint - float(env["temperature_c"])) * 0.28, 1)
    if device_id in {"light.living", "curtain.living"}:
        daylight = 220 * (curtain.get("position", 0) / 100)
        artificial = light.get("brightness", 0) * 7 if light.get("on") else 0
        env["lux"] = int(max(20, min(1200, daylight + artificial)))
    env["ts"] = now_iso()


async def apply_command(
    device_id: str,
    action: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    source: str = "api",
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    params = params or {}
    device = get_device(device_id)
    state = device["state"]

    if device_id == "ac.main":
        if action == "power":
            state["power"] = bool(params.get("on", params.get("power", True)))
        elif action == "set_temp":
            state["setpoint"] = coerce_temp(params.get("temp", params.get("setpoint")), state.get("setpoint", 24))
            state["power"] = True
        elif action == "set_mode":
            state["mode"] = str(params.get("mode", state.get("mode", "cool")))
            state["power"] = True
        elif action == "set_fan":
            state["fan_speed"] = str(params.get("speed", params.get("fan_speed", "auto")))
            state["power"] = True
        else:
            raise HTTPException(status_code=400, detail=f"unsupported action for {device_id}: {action}")

    elif device_id == "light.living":
        if action == "set_on":
            state["on"] = bool(params.get("on", True))
            if not state["on"]:
                state["brightness"] = 0
            elif state.get("brightness", 0) == 0:
                state["brightness"] = 65
        elif action == "set_brightness":
            state["brightness"] = coerce_percent(params.get("brightness"), state.get("brightness", 0))
            state["on"] = state["brightness"] > 0
        elif action == "set_cct":
            state["cct"] = int(params.get("cct", state.get("cct", 4200)))
        else:
            raise HTTPException(status_code=400, detail=f"unsupported action for {device_id}: {action}")

    elif device_id == "curtain.living":
        if action == "open":
            state["position"] = coerce_percent(params.get("position", 100), 100)
            state["moving"] = False
        elif action == "close":
            state["position"] = coerce_percent(params.get("position", 0), 0)
            state["moving"] = False
        elif action == "set_position":
            state["position"] = coerce_percent(params.get("position"), state.get("position", 0))
            state["moving"] = False
        else:
            raise HTTPException(status_code=400, detail=f"unsupported action for {device_id}: {action}")

    else:
        raise HTTPException(status_code=400, detail=f"{device_id} is read-only")

    update_environment_after_command(device_id)
    device_payload = copy.deepcopy(device)
    await publish_event(
        {
            "type": "device.command_applied",
            "source": source,
            "trace_id": trace_id,
            "device_id": device_id,
            "action": action,
            "params": params,
            "device_state": copy.deepcopy(state),
            "state": clone_state(),
        }
    )
    return device_payload


async def activate_scene(scene: str, source: str = "api") -> List[Dict[str, Any]]:
    global ACTIVE_SCENE
    scene_id = scene.strip().lower()
    scene_map = {
        "movie": [
            ("light.living", "set_brightness", {"brightness": 30}),
            ("curtain.living", "close", {"position": 20}),
            ("ac.main", "set_temp", {"temp": 24}),
        ],
        "sleep": [
            ("light.living", "set_brightness", {"brightness": 8}),
            ("curtain.living", "close", {"position": 0}),
            ("ac.main", "set_temp", {"temp": 26}),
            ("ac.main", "set_fan", {"speed": "quiet"}),
        ],
        "away": [
            ("light.living", "set_on", {"on": False}),
            ("curtain.living", "close", {"position": 0}),
            ("ac.main", "power", {"on": False}),
        ],
        "welcome": [
            ("light.living", "set_brightness", {"brightness": 85}),
            ("curtain.living", "open", {"position": 85}),
            ("ac.main", "set_temp", {"temp": 24}),
        ],
    }
    if scene_id not in scene_map:
        raise HTTPException(status_code=404, detail=f"unknown scene: {scene}")
    results = []
    for device_id, action, params in scene_map[scene_id]:
        results.append(await apply_command(device_id, action, params, source=source))
    ACTIVE_SCENE = scene_id
    await publish_event({"type": "scene.activated", "source": source, "scene": scene_id, "state": clone_state()})
    return results


def extract_first_number(text: str) -> Optional[float]:
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return float(match.group(1)) if match else None


def parse_chat_actions(message: str) -> List[Dict[str, Any]]:
    text = message.lower().replace("％", "%")
    number = extract_first_number(text)
    actions: List[Dict[str, Any]] = []

    if any(key in text for key in ["观影", "电影", "影院", "movie"]):
        return [{"kind": "scene", "scene": "movie"}]
    if any(key in text for key in ["睡眠", "睡觉", "晚安", "sleep"]):
        return [{"kind": "scene", "scene": "sleep"}]
    if any(key in text for key in ["离家", "出门", "away"]):
        return [{"kind": "scene", "scene": "away"}]
    if any(key in text for key in ["回家", "欢迎", "welcome"]):
        return [{"kind": "scene", "scene": "welcome"}]

    if any(key in text for key in ["空调", "温度", "热", "冷", "ac"]):
        if any(key in text for key in ["关", "关闭", "off"]):
            actions.append({"kind": "command", "device_id": "ac.main", "action": "power", "params": {"on": False}})
        elif any(key in text for key in ["开", "打开", "on"]):
            actions.append({"kind": "command", "device_id": "ac.main", "action": "power", "params": {"on": True}})
        if number is not None:
            actions.append({"kind": "command", "device_id": "ac.main", "action": "set_temp", "params": {"temp": number}})
        elif "热" in text:
            actions.append({"kind": "command", "device_id": "ac.main", "action": "set_temp", "params": {"temp": 23}})
        elif "冷" in text:
            actions.append({"kind": "command", "device_id": "ac.main", "action": "set_temp", "params": {"temp": 26}})

    if any(key in text for key in ["灯", "亮度", "light"]):
        if any(key in text for key in ["关", "关闭", "off"]):
            actions.append({"kind": "command", "device_id": "light.living", "action": "set_on", "params": {"on": False}})
        elif number is not None:
            actions.append({"kind": "command", "device_id": "light.living", "action": "set_brightness", "params": {"brightness": number}})
        elif any(key in text for key in ["开", "打开", "on"]):
            actions.append({"kind": "command", "device_id": "light.living", "action": "set_on", "params": {"on": True}})
        elif any(key in text for key in ["暗", "调暗"]):
            actions.append({"kind": "command", "device_id": "light.living", "action": "set_brightness", "params": {"brightness": 30}})
        elif any(key in text for key in ["亮", "调亮"]):
            actions.append({"kind": "command", "device_id": "light.living", "action": "set_brightness", "params": {"brightness": 80}})

    if any(key in text for key in ["窗帘", "curtain"]):
        if any(key in text for key in ["一半", "半开"]):
            actions.append({"kind": "command", "device_id": "curtain.living", "action": "set_position", "params": {"position": 50}})
        elif number is not None:
            actions.append({"kind": "command", "device_id": "curtain.living", "action": "set_position", "params": {"position": number}})
        elif any(key in text for key in ["打开", "全开", "开"]):
            actions.append({"kind": "command", "device_id": "curtain.living", "action": "open", "params": {"position": 100}})
        elif any(key in text for key in ["关闭", "关上", "合上", "关"]):
            actions.append({"kind": "command", "device_id": "curtain.living", "action": "close", "params": {"position": 0}})

    return actions


def compute_suggestions() -> List[Dict[str, Any]]:
    env = DEVICES["sensor.env"]["state"]
    ac = DEVICES["ac.main"]["state"]
    light = DEVICES["light.living"]["state"]
    curtain = DEVICES["curtain.living"]["state"]
    suggestions: List[Dict[str, Any]] = []

    if env["temperature_c"] >= 27 and (not ac.get("power") or ac.get("setpoint", 24) > 24):
        suggestions.append(
            {
                "id": "cool_down",
                "title": "检测到室温偏高",
                "message": "建议将空调调整到 23 度，并保持自动风速。",
                "action": {"device_id": "ac.main", "action": "set_temp", "params": {"temp": 23}},
            }
        )
    if env["lux"] < 200 and light.get("brightness", 0) < 45:
        suggestions.append(
            {
                "id": "raise_light",
                "title": "当前光照不足",
                "message": "建议把客厅灯光提高到 65%。",
                "action": {"device_id": "light.living", "action": "set_brightness", "params": {"brightness": 65}},
            }
        )
    if env["lux"] > 750 and curtain.get("position", 0) > 70:
        suggestions.append(
            {
                "id": "soften_daylight",
                "title": "阳光较强",
                "message": "建议将窗帘调整到 45%，降低眩光。",
                "action": {"device_id": "curtain.living", "action": "set_position", "params": {"position": 45}},
            }
        )
    if not suggestions:
        suggestions.append(
            {
                "id": "comfort_ok",
                "title": "舒适状态稳定",
                "message": "温度、光照和窗帘状态处于适合演示的舒适区间。",
                "action": None,
            }
        )
    return suggestions[:3]


def build_reply(actions: List[Dict[str, Any]]) -> str:
    if not actions:
        return "我没有识别到可执行的设备动作。可以试试：把空调调到 23 度、灯光调到 30%、窗帘打开一半、进入观影模式。"
    if len(actions) == 1 and actions[0].get("kind") == "scene":
        names = {"movie": "观影模式", "sleep": "睡眠模式", "away": "离家模式", "welcome": "欢迎回家模式"}
        return f"已为你切换到{names.get(actions[0]['scene'], actions[0]['scene'])}，设备状态正在同步到屏幕。"
    device_names = {"ac.main": "空调", "light.living": "灯光", "curtain.living": "窗帘"}
    changed = [device_names.get(action.get("device_id"), action.get("device_id", "设备")) for action in actions]
    return "已执行：" + "、".join(dict.fromkeys(changed)) + "。状态已实时更新。"


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "attrax-home", "time": now_iso()}


@router.get("/state")
async def state() -> Dict[str, Any]:
    return clone_state()


@router.post("/devices/{device_id}/commands")
async def command_device(device_id: str, body: CommandRequest) -> Dict[str, Any]:
    device = await apply_command(device_id, body.action, body.params, source=body.source, trace_id=body.trace_id)
    return {"ok": True, "device": device, "state": clone_state()}


@router.post("/scene")
async def scene(body: SceneRequest) -> Dict[str, Any]:
    devices = await activate_scene(body.scene, source=body.source)
    return {"ok": True, "scene": ACTIVE_SCENE, "devices": devices, "state": clone_state()}


@router.post("/chat")
async def chat(body: ChatRequest) -> Dict[str, Any]:
    global LAST_REPLY
    message = body.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="message is required")

    await publish_event({"type": "chat.user_message", "source": "chat", "message": message, "session_id": body.session_id})
    actions = parse_chat_actions(message)
    await publish_event({"type": "intent.parsed", "source": "rule_parser", "message": message, "actions": actions, "session_id": body.session_id})

    applied: List[Dict[str, Any]] = []
    for action in actions:
        if action.get("kind") == "scene":
            applied.extend(await activate_scene(action["scene"], source="chat"))
        elif action.get("kind") == "command":
            applied.append(
                await apply_command(
                    action["device_id"],
                    action["action"],
                    action.get("params", {}),
                    source="chat",
                    trace_id=body.session_id,
                )
            )

    LAST_REPLY = build_reply(actions)
    await publish_event(
        {
            "type": "automation.suggestion",
            "source": "rule_engine",
            "message": "智能建议已刷新",
            "suggestions": compute_suggestions(),
            "state": clone_state(),
        }
    )
    return {"ok": True, "reply": LAST_REPLY, "actions": actions, "applied": applied, "state": clone_state()}


@router.post("/reset")
async def reset() -> Dict[str, Any]:
    global DEVICES, ACTIVE_SCENE, LAST_REPLY
    DEVICES = seed_devices()
    ACTIVE_SCENE = "manual"
    LAST_REPLY = "演示状态已重置。"
    RECENT_EVENTS.clear()
    await publish_event({"type": "system.reset", "source": "api", "message": LAST_REPLY, "state": clone_state()})
    return {"ok": True, "state": clone_state()}


@router.get("/events/stream")
async def events_stream() -> StreamingResponse:
    async def event_generator():
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        SUBSCRIBERS.add(queue)
        await queue.put({"type": "hello", "source": "events", "message": "Attrax home event stream connected", "state": clone_state()})
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            SUBSCRIBERS.discard(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )
