"""Dynamic home environment engine shared by the simulator and visualization app."""

from __future__ import annotations

from datetime import datetime, timedelta
import math
import random
import time
from typing import Any

from pydantic import BaseModel, Field

from app.core.config import load_yaml_file
from app.environment.device_hub import DeviceHub
from app.environment.home_state import DeviceState, HomeState, OutdoorState, SensorSnapshot
from app.environment.sensor_hub import SensorHub
from app.planning.action import PlannedAction


class DynamicSimulationConfig(BaseModel):
    """Config for the dynamic home environment engine."""

    start_time: str = "2026-04-10T18:00:00+08:00"
    time_scale_minutes_per_real_second: float = 3.0
    random_seed: int = 7
    outdoor: OutdoorState = Field(default_factory=OutdoorState)


class DynamicHomeEnvironment:
    """Maintains a slowly changing outdoor world and derived indoor sensor state."""

    def __init__(
        self,
        *,
        sensors: SensorSnapshot | None = None,
        devices: DeviceState | None = None,
        config: DynamicSimulationConfig | None = None,
    ) -> None:
        self.config = config or DynamicSimulationConfig()
        self._rng = random.Random(self.config.random_seed)
        initial_devices = (devices or DeviceState()).model_copy(deep=True)
        initial_sensors = (sensors or SensorSnapshot()).model_copy(deep=True)
        self._initial_devices = initial_devices.model_copy(deep=True)
        self._initial_sensors = initial_sensors.model_copy(deep=True)
        self._current_time = datetime.fromisoformat(self.config.start_time)
        self._outdoor = self.config.outdoor.model_copy(deep=True)
        self._devices = initial_devices
        self._sensors = initial_sensors
        self._last_sync = time.monotonic()
        self._refresh_derived_state()

    @classmethod
    def from_config_paths(
        cls,
        *,
        sensors_config_path,
        devices_config_path,
        simulator_config_path,
    ) -> "DynamicHomeEnvironment":
        simulator_payload = load_yaml_file(simulator_config_path)
        config = DynamicSimulationConfig(**simulator_payload) if simulator_payload else None
        sensors = SensorHub.from_config(sensors_config_path).get_snapshot()
        devices = DeviceHub.from_config(devices_config_path).get_state()
        return cls(sensors=sensors, devices=devices, config=config)

    def get_home_state(self) -> HomeState:
        self.sync_with_wall_clock()
        return self._build_home_state()

    def reset(self) -> HomeState:
        self._rng.seed(self.config.random_seed)
        self._current_time = datetime.fromisoformat(self.config.start_time)
        self._outdoor = self.config.outdoor.model_copy(deep=True)
        self._devices = self._initial_devices.model_copy(deep=True)
        self._sensors = self._initial_sensors.model_copy(deep=True)
        self._last_sync = time.monotonic()
        self._refresh_derived_state()
        return self._build_home_state()

    def apply_actions(self, actions: list[PlannedAction]) -> HomeState:
        self.sync_with_wall_clock()
        for action in actions:
            if action.device_id in self._devices.air_conditioners:
                setattr(self._devices.air_conditioners[action.device_id], action.attribute, action.value)
                continue
            if action.device_id in self._devices.lights:
                setattr(self._devices.lights[action.device_id], action.attribute, action.value)
                continue
            if action.device_id == "music_player":
                setattr(self._devices.music_player, action.attribute, action.value)
                continue
            if action.device_id in self._devices.fans:
                setattr(self._devices.fans[action.device_id], action.attribute, action.value)
                continue
            if action.device_id in self._devices.covers:
                setattr(self._devices.covers[action.device_id], action.attribute, action.value)
                continue
            if action.device_id in self._devices.locks:
                setattr(self._devices.locks[action.device_id], action.attribute, action.value)
                continue
            if action.device_id in self._devices.switches:
                setattr(self._devices.switches[action.device_id], action.attribute, action.value)
                continue
            if action.device_id in self._devices.appliances:
                setattr(self._devices.appliances[action.device_id], action.attribute, action.value)
                continue
            raise KeyError(f"Unknown device_id: {action.device_id}")

        self.tick(minutes=3.0)
        return self.get_home_state()

    _TIME_OF_DAY_REPRESENTATIVE_HOUR: dict[str, int] = {
        "dawn": 6, "morning": 10, "afternoon": 15, "evening": 19, "night": 23,
    }

    def apply_overrides(
        self,
        sensors: dict[str, Any] | None = None,
        outdoor: dict[str, Any] | None = None,
        devices: dict[str, dict[str, dict[str, Any]]] | None = None,
    ) -> HomeState:
        """Override individual sensor / outdoor / device fields without resetting.

        Useful for demo presets and ad-hoc tuning from the dashboard.
        Unknown keys are silently ignored so the caller can pass partial payloads.
        time_of_day is honored by shifting the simulator clock to a representative hour.
        """
        if sensors:
            tod = sensors.get("time_of_day")
            if tod and tod in self._TIME_OF_DAY_REPRESENTATIVE_HOUR:
                self._current_time = self._current_time.replace(
                    hour=self._TIME_OF_DAY_REPRESENTATIVE_HOUR[tod],
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            for key, value in sensors.items():
                if key in ("time_of_day", "current_time"):
                    continue  # 由 _refresh_derived_state 派生
                if hasattr(self._sensors, key):
                    setattr(self._sensors, key, value)
        if outdoor:
            for key, value in outdoor.items():
                if hasattr(self._outdoor, key):
                    setattr(self._outdoor, key, value)
        if devices:
            # devices = {"air_conditioners": {"living_room_ac_1": {"power": True}}, ...}
            for category, dev_map in devices.items():
                target_category = getattr(self._devices, category, None)
                if target_category is None or not isinstance(dev_map, dict):
                    continue
                if isinstance(target_category, dict):
                    for dev_id, attrs in dev_map.items():
                        if dev_id in target_category and isinstance(attrs, dict):
                            for k, v in attrs.items():
                                if hasattr(target_category[dev_id], k):
                                    setattr(target_category[dev_id], k, v)
                else:
                    # singletons like music_player
                    for k, v in dev_map.items():
                        if hasattr(target_category, k):
                            setattr(target_category, k, v)
        self._refresh_derived_state()
        self._last_sync = time.monotonic()
        return self._build_home_state()

    def sync_with_wall_clock(self) -> None:
        elapsed_seconds = max(0.0, time.monotonic() - self._last_sync)
        if elapsed_seconds < 0.25:
            return
        self._last_sync = time.monotonic()
        self.tick(minutes=elapsed_seconds * self.config.time_scale_minutes_per_real_second)

    def tick(self, minutes: float = 5.0) -> HomeState:
        self._current_time += timedelta(minutes=minutes)
        self._update_outdoor(minutes)
        self._update_occupancy()
        self._update_indoor_sensors(minutes)
        self._refresh_derived_state()
        self._last_sync = time.monotonic()
        return self._build_home_state()

    def snapshot_payload(self) -> dict[str, Any]:
        state = self.get_home_state()
        return {
            "time": state.sensors.current_time,
            "time_of_day": state.sensors.time_of_day,
            "quiet_hours": state.sensors.quiet_hours,
            "outdoor": state.outdoor.model_dump(mode="json"),
            "sensors": state.sensors.model_dump(mode="json"),
            "devices": state.devices.model_dump(mode="json"),
        }

    def _build_home_state(self) -> HomeState:
        return HomeState(
            sensors=self._sensors.model_copy(deep=True),
            devices=self._devices.model_copy(deep=True),
            outdoor=self._outdoor.model_copy(deep=True),
        )

    def _update_outdoor(self, minutes: float) -> None:
        hour = self._current_time.hour + (self._current_time.minute / 60.0)
        daylight_curve = max(0.0, math.sin(math.pi * (hour - 6.0) / 12.0))
        baseline_temp = 18.0 + daylight_curve * 12.0

        self._outdoor.cloud_cover_pct = self._clamp_int(
            self._outdoor.cloud_cover_pct + self._rng.randint(-4, 4),
            0,
            100,
        )
        self._outdoor.humidity_pct = self._clamp_int(
            self._outdoor.humidity_pct + self._rng.randint(-2, 2),
            35,
            96,
        )
        wind_target = max(0.5, self._outdoor.wind_speed_mps + self._rng.uniform(-0.25, 0.25))
        self._outdoor.wind_speed_mps = round(min(10.0, wind_target), 1)

        cloud_factor = 1.0 - (self._outdoor.cloud_cover_pct / 130.0)
        light_target = max(0.0, min(100.0, daylight_curve * 100.0 * cloud_factor))
        self._outdoor.outdoor_light_level = self._clamp_int(
            int(round(light_target + self._rng.uniform(-2.0, 2.0))),
            0,
            100,
        )

        weather_bias = {
            "clear": 1.5,
            "cloudy": -0.8,
            "rainy": -2.5,
            "windy": -1.2,
        }
        condition = self._infer_weather()
        self._outdoor.weather = condition
        temperature_target = baseline_temp + weather_bias[condition]
        temperature_delta = (temperature_target - self._outdoor.outdoor_temperature_c) * min(0.35, minutes / 40.0)
        temperature_delta += self._rng.uniform(-0.18, 0.18)
        self._outdoor.outdoor_temperature_c = round(
            self._clamp_float(self._outdoor.outdoor_temperature_c + temperature_delta, 8.0, 39.0),
            1,
        )

    def _update_occupancy(self) -> None:
        hour = self._current_time.hour + (self._current_time.minute / 60.0)
        living_room_prob = 0.75 if 18.0 <= hour < 23.0 else 0.45 if 7.0 <= hour < 18.0 else 0.12
        bedroom_prob = 0.82 if hour >= 22.0 or hour < 7.0 else 0.22
        if self._devices.appliances["robot_vacuum_1"].status == "cleaning":
            living_room_prob = max(0.0, living_room_prob - 0.25)
        self._sensors.occupancy["living_room"] = self._rng.random() < living_room_prob
        self._sensors.occupancy["bedroom"] = self._rng.random() < bedroom_prob

    def _update_indoor_sensors(self, minutes: float) -> None:
        temp_blend = min(0.25, minutes / 60.0)
        humidity_blend = min(0.22, minutes / 70.0)

        living_room_ac = self._devices.air_conditioners["living_room_ac_1"]
        bedroom_ac = self._devices.air_conditioners["bedroom_ac_1"]
        living_room_fan = self._devices.fans["living_room_fan_1"]
        bedroom_fan = self._devices.fans["bedroom_fan_1"]
        living_room_cover = self._devices.covers["living_room_curtain"]
        bedroom_cover = self._devices.covers["bedroom_blinds"]
        purifier = self._devices.switches["air_purifier"]
        humidifier = self._devices.switches["bedroom_humidifier"]
        living_room_occ = self._sensors.occupancy.get("living_room", False)
        bedroom_occ = self._sensors.occupancy.get("bedroom", False)

        self._sensors.room_temperature_c = round(
            self._next_room_temperature(
                current=self._sensors.room_temperature_c,
                outdoor=self._outdoor.outdoor_temperature_c,
                ac_power=living_room_ac.power,
                ac_target=living_room_ac.target_temperature,
                fan_speed=living_room_ac.fan_speed,
                occupied=living_room_occ,
                blend=temp_blend,
                circulation_power=living_room_fan.power,
                circulation_speed=living_room_fan.speed,
                cover_position=living_room_cover.position,
            ),
            1,
        )
        self._sensors.bedroom_temperature_c = round(
            self._next_room_temperature(
                current=self._sensors.bedroom_temperature_c,
                outdoor=self._outdoor.outdoor_temperature_c - 0.8,
                ac_power=bedroom_ac.power,
                ac_target=bedroom_ac.target_temperature,
                fan_speed=bedroom_ac.fan_speed,
                occupied=bedroom_occ,
                blend=temp_blend,
                circulation_power=bedroom_fan.power,
                circulation_speed=bedroom_fan.speed,
                cover_position=bedroom_cover.position,
            ),
            1,
        )

        humidity_target = self._outdoor.humidity_pct - (7 if living_room_ac.power else 0)
        humidity_target -= 2 if purifier.power else 0
        humidity_target += 4 if humidifier.power else 0
        humidity_target += 3 if living_room_occ else 0
        humidity_delta = (humidity_target - self._sensors.room_humidity_pct) * humidity_blend
        humidity_delta += self._rng.uniform(-0.6, 0.6)
        self._sensors.room_humidity_pct = self._clamp_int(
            int(round(self._sensors.room_humidity_pct + humidity_delta)),
            28,
            85,
        )

        main_light = self._devices.lights["living_room_main"]
        cover_multiplier = {"open": 1.0, "half": 0.72, "closed": 0.45}.get(living_room_cover.position, 0.8)
        base_indoor_light = self._outdoor.outdoor_light_level * 0.45 * cover_multiplier
        if main_light.power:
            base_indoor_light += max(8.0, main_light.brightness * 0.72)
        if self._devices.music_player.power:
            base_indoor_light += 1.0
        self._sensors.ambient_light_level = self._clamp_int(
            int(round(base_indoor_light + self._rng.uniform(-2.5, 2.5))),
            0,
            100,
        )

    def _refresh_derived_state(self) -> None:
        hour = self._current_time.hour + (self._current_time.minute / 60.0)
        self._sensors.current_time = self._current_time.isoformat()
        self._sensors.quiet_hours = hour >= 22.0 or hour < 7.0
        if 5.0 <= hour < 8.0:
            self._sensors.time_of_day = "dawn"
        elif 8.0 <= hour < 12.0:
            self._sensors.time_of_day = "morning"
        elif 12.0 <= hour < 17.0:
            self._sensors.time_of_day = "afternoon"
        elif 17.0 <= hour < 21.0:
            self._sensors.time_of_day = "evening"
        else:
            self._sensors.time_of_day = "night"

    def _infer_weather(self) -> str:
        if self._outdoor.humidity_pct >= 82 and self._outdoor.cloud_cover_pct >= 70:
            return "rainy"
        if self._outdoor.wind_speed_mps >= 6.0 and self._outdoor.cloud_cover_pct < 65:
            return "windy"
        if self._outdoor.cloud_cover_pct >= 48:
            return "cloudy"
        return "clear"

    def _next_room_temperature(
        self,
        *,
        current: float,
        outdoor: float,
        ac_power: bool,
        ac_target: int,
        fan_speed: str,
        occupied: bool,
        blend: float,
        circulation_power: bool,
        circulation_speed: str,
        cover_position: str,
    ) -> float:
        outdoor_pull = (outdoor - current) * blend
        cover_modifier = {"open": 0.18, "half": 0.08, "closed": -0.03}.get(cover_position, 0.05)
        occupancy_heat = 0.18 if occupied else -0.05
        ac_effect = 0.0
        if ac_power:
            fan_modifier = {"low": 0.35, "medium": 0.5, "high": 0.7, "auto": 0.48}.get(fan_speed, 0.45)
            ac_effect = -max(0.0, current - ac_target + 0.25) * fan_modifier
        circulation_effect = 0.0
        if circulation_power:
            circulation_effect = {"low": -0.1, "medium": -0.18, "high": -0.28}.get(circulation_speed, -0.16)
        noise = self._rng.uniform(-0.12, 0.12)
        return self._clamp_float(
            current + outdoor_pull + cover_modifier + occupancy_heat + ac_effect + circulation_effect + noise,
            18.0,
            33.0,
        )

    @staticmethod
    def _clamp_float(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    @staticmethod
    def _clamp_int(value: int, lower: int, upper: int) -> int:
        return max(lower, min(upper, value))
