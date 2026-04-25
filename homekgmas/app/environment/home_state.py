"""Environment state models for the local smart-home simulator."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SensorSnapshot(BaseModel):
    """Current simulated sensor readings."""

    room_temperature_c: float = 27.5
    bedroom_temperature_c: float = 26.0
    room_humidity_pct: int = 52
    ambient_light_level: int = 30
    occupancy: dict[str, bool] = Field(
        default_factory=lambda: {"living_room": True, "bedroom": False}
    )
    current_time: str = "2026-04-10T18:00:00+08:00"
    time_of_day: str = "evening"
    quiet_hours: bool = False


class OutdoorState(BaseModel):
    """Current outdoor conditions used by the simulator."""

    weather: str = "clear"
    outdoor_temperature_c: float = 29.0
    outdoor_light_level: int = 70
    humidity_pct: int = 64
    wind_speed_mps: float = 2.8
    cloud_cover_pct: int = 18


class AirConditionerState(BaseModel):
    """A single AC state."""

    power: bool = False
    target_temperature: int = 26
    fan_speed: str = "auto"
    mode: str = "cool"


class LightState(BaseModel):
    """A single light state."""

    power: bool = False
    brightness: int = 50
    color: str = "neutral"
    mode: str = "static"
    group: str = "default"


class MusicPlayerState(BaseModel):
    """Music player state."""

    power: bool = False
    playlist: str = "quiet_focus"
    volume: int = 20
    input_source: str = "home"
    brightness: int = 50
    equalizer: str = "balanced"
    media_track: int = 1


class FanState(BaseModel):
    """A single circulation fan state."""

    power: bool = False
    speed: str = "medium"
    oscillate: bool = False
    group: str = "default"


class CoverState(BaseModel):
    """A curtain or blind state."""

    position: str = "open"
    group: str = "default"


class LockState(BaseModel):
    """A smart lock state."""

    locked: bool = True
    armed: bool = False
    alarm_volume: int = 50
    group: str = "entry"


class SwitchDeviceState(BaseModel):
    """A simple on-off device with a lightweight mode field."""

    power: bool = False
    mode: str = "auto"
    humidity: int = 50
    group: str = "default"


class ApplianceState(BaseModel):
    """A small appliance state."""

    power: bool = False
    mode: str = "idle"
    status: str = "docked"
    group: str = "default"


class DeviceState(BaseModel):
    """Current device states in the simulator."""

    air_conditioners: dict[str, AirConditionerState] = Field(
        default_factory=lambda: {
            "living_room_ac_1": AirConditionerState(),
            "bedroom_ac_1": AirConditionerState(mode="sleep"),
        }
    )
    lights: dict[str, LightState] = Field(
        default_factory=lambda: {
            "living_room_main": LightState(group="living_room"),
            "bedroom_lamp": LightState(brightness=40, group="bedroom"),
        }
    )
    music_player: MusicPlayerState = Field(default_factory=MusicPlayerState)
    fans: dict[str, FanState] = Field(
        default_factory=lambda: {
            "living_room_fan_1": FanState(group="living_room"),
            "bedroom_fan_1": FanState(group="bedroom"),
        }
    )
    covers: dict[str, CoverState] = Field(
        default_factory=lambda: {
            "living_room_curtain": CoverState(group="living_room"),
            "bedroom_blinds": CoverState(position="half", group="bedroom"),
        }
    )
    locks: dict[str, LockState] = Field(
        default_factory=lambda: {
            "front_door_lock": LockState(group="entry"),
        }
    )
    switches: dict[str, SwitchDeviceState] = Field(
        default_factory=lambda: {
            "air_purifier": SwitchDeviceState(group="living_room"),
            "bedroom_humidifier": SwitchDeviceState(group="bedroom"),
        }
    )
    appliances: dict[str, ApplianceState] = Field(
        default_factory=lambda: {
            "robot_vacuum_1": ApplianceState(group="living_room"),
        }
    )


class HomeState(BaseModel):
    """Combined environment state."""

    sensors: SensorSnapshot
    devices: DeviceState
    outdoor: OutdoorState = Field(default_factory=OutdoorState)
