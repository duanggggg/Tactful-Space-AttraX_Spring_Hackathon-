"""Environment preset and override routes for demo / dashboard control."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.environment.home_state import HomeState
from app.environment.simulator import HomeSimulator


# ---- Built-in demo presets aligned with Attrax_competition/demo_script.md ----

PRESETS: dict[str, dict[str, Any]] = {
    "客户来访": {
        "label": "客户来访 · 软约束推理",
        "description": "客户即将到访，环境略闷、灯偏暗，等待 agent 自动调温/调灯/切屏",
        "suggested_prompt": "再过十分钟客户要来看 demo，帮我准备一下",
        "sensors": {
            "room_temperature_c": 28.0,
            "bedroom_temperature_c": 27.0,
            "room_humidity_pct": 55,
            "ambient_light_level": 25,
            "occupancy": {"living_room": True, "bedroom": False},
            "time_of_day": "afternoon",
            "quiet_hours": False,
        },
        "outdoor": {
            "weather": "clear",
            "outdoor_temperature_c": 30.0,
            "outdoor_light_level": 75,
            "humidity_pct": 60,
            "cloud_cover_pct": 18,
        },
        "devices": {
            "lights": {"living_room_main": {"power": False, "brightness": 25}},
            "air_conditioners": {
                "living_room_ac_1": {"power": False, "target_temperature": 26}
            },
        },
    },
    "闷热体感": {
        "label": "闷热体感 · 多 agent 协商",
        "description": "27.5°C 高湿度，用户怕直吹冷风，看 AC 和灯如何跨域协商",
        "suggested_prompt": "感觉有点闷，但又怕开空调直吹",
        "sensors": {
            "room_temperature_c": 27.5,
            "bedroom_temperature_c": 26.5,
            "room_humidity_pct": 70,
            "ambient_light_level": 45,
            "occupancy": {"living_room": True, "bedroom": False},
            "time_of_day": "afternoon",
            "quiet_hours": False,
        },
        "outdoor": {
            "weather": "cloudy",
            "outdoor_temperature_c": 31.0,
            "outdoor_light_level": 55,
            "humidity_pct": 75,
            "cloud_cover_pct": 60,
        },
        "devices": {
            "air_conditioners": {"living_room_ac_1": {"power": False}},
            "fans": {"living_room_fan_1": {"power": False}},
        },
    },
    "准备出门": {
        "label": "准备出门 · 跨域协同",
        "description": "用户即将短暂离开，agent 应进入节能 + 引导亮度模式",
        "suggested_prompt": "我出去接个人，半小时就回",
        "sensors": {
            "room_temperature_c": 25.0,
            "bedroom_temperature_c": 25.0,
            "room_humidity_pct": 50,
            "ambient_light_level": 50,
            "occupancy": {"living_room": True, "bedroom": False},
            "time_of_day": "evening",
            "quiet_hours": False,
        },
        "outdoor": {
            "weather": "clear",
            "outdoor_temperature_c": 24.0,
            "outdoor_light_level": 35,
            "humidity_pct": 55,
        },
        "devices": {
            "lights": {"living_room_main": {"power": True, "brightness": 70}},
            "air_conditioners": {
                "living_room_ac_1": {
                    "power": True,
                    "target_temperature": 25,
                    "mode": "cool",
                }
            },
        },
    },
    "默认": {
        "label": "默认初始状态",
        "description": "重置到系统初始的 27.5°C / 52% / 30 lux",
        "suggested_prompt": "",
        "sensors": {
            "room_temperature_c": 27.5,
            "bedroom_temperature_c": 26.0,
            "room_humidity_pct": 52,
            "ambient_light_level": 30,
            "occupancy": {"living_room": True, "bedroom": False},
            "time_of_day": "evening",
            "quiet_hours": False,
        },
        "outdoor": {
            "weather": "clear",
            "outdoor_temperature_c": 29.0,
            "outdoor_light_level": 70,
            "humidity_pct": 64,
            "cloud_cover_pct": 18,
        },
        "devices": {},
    },
}


class PresetRequest(BaseModel):
    name: str


class OverrideRequest(BaseModel):
    sensors: Optional[dict[str, Any]] = Field(default=None)
    outdoor: Optional[dict[str, Any]] = Field(default=None)
    devices: Optional[dict[str, dict[str, dict[str, Any]]]] = Field(default=None)


def build_environment_router(simulator: HomeSimulator) -> APIRouter:
    router = APIRouter(prefix="/environment", tags=["environment"])

    @router.get("/presets")
    def list_presets() -> dict[str, Any]:
        return {
            "presets": [
                {
                    "name": name,
                    "label": data["label"],
                    "description": data["description"],
                    "suggested_prompt": data.get("suggested_prompt", ""),
                }
                for name, data in PRESETS.items()
            ]
        }

    @router.post("/preset", response_model=HomeState)
    def apply_preset(request: PresetRequest) -> HomeState:
        preset = PRESETS.get(request.name)
        if preset is None:
            raise HTTPException(
                status_code=404,
                detail=f"unknown preset: {request.name}. Available: {list(PRESETS.keys())}",
            )
        return simulator.apply_overrides(
            sensors=preset.get("sensors"),
            outdoor=preset.get("outdoor"),
            devices=preset.get("devices") or None,
        )

    @router.post("/override", response_model=HomeState)
    def apply_override(request: OverrideRequest) -> HomeState:
        if not any([request.sensors, request.outdoor, request.devices]):
            raise HTTPException(status_code=400, detail="must supply at least one of: sensors / outdoor / devices")
        return simulator.apply_overrides(
            sensors=request.sensors,
            outdoor=request.outdoor,
            devices=request.devices,
        )

    @router.get("/state", response_model=HomeState)
    def get_current_state() -> HomeState:
        return simulator.get_home_state()

    return router
