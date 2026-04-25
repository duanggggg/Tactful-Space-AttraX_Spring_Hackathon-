"""Standalone web environment with gradual indoor updates driven by agent state."""

from __future__ import annotations

from datetime import datetime, timedelta
import math
import random
import time

from app.agents.web.action_catalog import WebActionSpec, get_web_action, list_web_actions
from app.environment.web_state import (
    WebAgentState,
    WebIndoorState,
    WebMetaState,
    WebOutdoorState,
    WebSimulatorSnapshot,
)


class WebHomeEnvironment:
    """A web-facing simulator where actions update device state and room conditions over time."""

    def __init__(self) -> None:
        self._rng = random.Random(13)
        self._initial_meta = WebMetaState()
        self._initial_outdoor = WebOutdoorState()
        self._initial_indoor = WebIndoorState()
        self._initial_agents = WebAgentState()
        self._current_time = datetime.fromisoformat(self._initial_meta.current_time)
        self._meta = self._initial_meta.model_copy(deep=True)
        self._outdoor = self._initial_outdoor.model_copy(deep=True)
        self._indoor = self._initial_indoor.model_copy(deep=True)
        self._agents = self._initial_agents.model_copy(deep=True)
        self._recent_events: list[str] = ["Web simulator initialized."]
        self._last_sync = time.monotonic()
        self._refresh_meta()

    def snapshot_payload(self) -> dict:
        """Return the current simulator snapshot."""

        self.sync_with_wall_clock()
        return self._snapshot().model_dump(mode="json")

    def action_catalog_payload(self) -> list[dict]:
        """Return the normalized action catalog for UI rendering."""

        return [item.model_dump(mode="json") for item in list_web_actions()]

    def reset(self) -> dict:
        """Reset the simulator to its initial state."""

        self._rng.seed(13)
        self._current_time = datetime.fromisoformat(self._initial_meta.current_time)
        self._meta = self._initial_meta.model_copy(deep=True)
        self._outdoor = self._initial_outdoor.model_copy(deep=True)
        self._indoor = self._initial_indoor.model_copy(deep=True)
        self._agents = self._initial_agents.model_copy(deep=True)
        self._recent_events = ["Web simulator reset."]
        self._last_sync = time.monotonic()
        self._refresh_meta()
        return self.snapshot_payload()

    def apply_action(self, action_key: str) -> dict:
        """Apply one catalog action and advance the simulation a small step."""

        self.sync_with_wall_clock()
        spec = get_web_action(action_key)
        self._apply_action_spec(spec)
        self._push_event(f"Applied {spec.label}.")
        self.tick(minutes=4.0)
        return self.snapshot_payload()

    def tick(self, minutes: float = 5.0) -> dict:
        """Advance the simulator and evolve outdoor plus indoor conditions."""

        self._current_time += timedelta(minutes=minutes)
        self._update_outdoor(minutes)
        self._update_indoor(minutes)
        self._refresh_meta()
        self._last_sync = time.monotonic()
        return self._snapshot().model_dump(mode="json")

    def sync_with_wall_clock(self) -> None:
        """Advance the simulation gradually when the UI is left open."""

        elapsed_seconds = max(0.0, time.monotonic() - self._last_sync)
        if elapsed_seconds < 0.3:
            return
        self._last_sync = time.monotonic()
        self.tick(minutes=elapsed_seconds * 2.8)

    def _snapshot(self) -> WebSimulatorSnapshot:
        return WebSimulatorSnapshot(
            meta=self._meta.model_copy(deep=True),
            outdoor=self._outdoor.model_copy(deep=True),
            indoor=self._indoor.model_copy(deep=True),
            agents=self._agents.model_copy(deep=True),
            recent_events=list(self._recent_events),
        )

    def _apply_action_spec(self, spec: WebActionSpec) -> None:
        room = spec.room
        params = spec.params

        if spec.agent_name == "air_conditioner_agent":
            unit = getattr(self._agents.air_conditioner, room)
            if "power" in params:
                unit.power = bool(params["power"])
            if unit.power:
                unit.mode = str(params.get("mode", unit.mode))
                unit.target_temp = int(params.get("target_temp", unit.target_temp))
                unit.fan_level = str(params.get("fan_level", unit.fan_level))
            elif spec.service == "turn_off":
                unit.mode = "off"
            return

        if spec.agent_name == "window_agent":
            getattr(self._agents.window, room).position = str(params["position"])
            return

        if spec.agent_name == "curtain_agent":
            getattr(self._agents.curtain, room).position = str(params["position"])
            return

        if spec.agent_name == "fan_agent":
            unit = getattr(self._agents.fan, room)
            if "power" in params:
                unit.power = bool(params["power"])
            if unit.power:
                unit.speed = str(params.get("speed", unit.speed))
            return

        if spec.agent_name == "fresh_air_agent":
            unit = getattr(self._agents.fresh_air, room)
            if "power" in params:
                unit.power = bool(params["power"])
            if unit.power:
                unit.flow_level = str(params.get("flow_level", unit.flow_level))
            return

        if spec.agent_name == "dehumidifier_agent":
            unit = getattr(self._agents.dehumidifier, room)
            if "power" in params:
                unit.power = bool(params["power"])
            if unit.power:
                unit.target_humidity = int(params.get("target_humidity", unit.target_humidity))
                unit.level = str(params.get("level", unit.level))
            return

        if spec.agent_name == "lighting_agent":
            unit = getattr(self._agents.lighting, room)
            if "power" in params:
                unit.power = bool(params["power"])
            if unit.power:
                unit.brightness = int(params.get("brightness", unit.brightness))
                unit.scene = str(params.get("scene", unit.scene))
            elif spec.service == "turn_off":
                unit.brightness = 0
                unit.scene = "off"
            return

        if spec.agent_name == "computer_agent":
            unit = getattr(self._agents.computer, room)
            if "power" in params:
                unit.power = bool(params["power"])
            if unit.power:
                unit.activity = str(params.get("activity", unit.activity))
                unit.volume = int(params.get("volume", unit.volume))
                unit.screen_brightness = int(params.get("screen_brightness", unit.screen_brightness))
            else:
                unit.activity = "idle"
                unit.volume = 0
                unit.screen_brightness = 0

    def _update_outdoor(self, minutes: float) -> None:
        scale = max(0.2, minutes / 5.0)
        hour = self._current_time.hour + (self._current_time.minute / 60.0)
        daylight_curve = max(0.0, math.sin(math.pi * (hour - 6.0) / 12.0))
        commuting_curve = max(0.0, math.sin(math.pi * (hour - 7.5) / 11.0))
        temperature_target = 19.0 + (daylight_curve * 13.0)
        humidity_target = 58 + int((1.0 - daylight_curve) * 16)
        brightness_target = int(daylight_curve * 100)
        noise_target = int(18 + (commuting_curve * 26) + ((1.0 - daylight_curve) * 6))
        air_target = 78 - int((humidity_target - 58) * 0.4) + int(self._rng.uniform(-2.0, 2.0))

        self._outdoor.outdoor_temp = round(
            self._approach(self._outdoor.outdoor_temp, temperature_target, 0.08 * scale) + self._rng.uniform(-0.08, 0.08),
            1,
        )
        self._outdoor.outdoor_humidity = self._clamp_int(
            int(round(self._approach(self._outdoor.outdoor_humidity, humidity_target, 0.12 * scale))),
            35,
            96,
        )
        self._outdoor.outdoor_brightness = self._clamp_int(
            int(round(self._approach(self._outdoor.outdoor_brightness, brightness_target, 0.18 * scale))),
            0,
            100,
        )
        self._outdoor.outdoor_noise = self._clamp_int(
            int(round(self._approach(self._outdoor.outdoor_noise, noise_target, 0.16 * scale))),
            10,
            90,
        )
        self._outdoor.outdoor_air = self._clamp_int(
            int(round(self._approach(self._outdoor.outdoor_air, air_target, 0.10 * scale))),
            25,
            98,
        )

        if self._outdoor.outdoor_humidity >= 82:
            self._outdoor.weather = "rainy"
        elif self._outdoor.outdoor_brightness < 22:
            self._outdoor.weather = "cloudy"
        else:
            self._outdoor.weather = "clear"

    def _update_indoor(self, minutes: float) -> None:
        scale = max(0.2, minutes / 5.0)
        self._update_room("living", scale)
        self._update_room("bedroom", scale)

    def _update_room(self, room: str, scale: float) -> None:
        room_state = getattr(self._indoor, room)
        ac = getattr(self._agents.air_conditioner, room)
        window = getattr(self._agents.window, room)
        curtain = getattr(self._agents.curtain, room)
        fan = getattr(self._agents.fan, room)
        fresh_air = getattr(self._agents.fresh_air, room)
        dehumidifier = getattr(self._agents.dehumidifier, room)
        lighting = getattr(self._agents.lighting, room)
        computer = getattr(self._agents.computer, room)

        window_exchange = {"closed": 0.04, "half": 0.10, "open": 0.18}[window.position]
        window_noise = {"closed": 0.12, "half": 0.38, "open": 0.68}[window.position]
        natural_light_factor = {"closed": 0.08, "half": 0.42, "open": 0.72}[window.position]
        curtain_light_factor = {"closed": 0.18, "half": 0.52, "open": 0.94}[curtain.position]
        sunlight_heat_factor = {"closed": 0.12, "half": 0.30, "open": 0.54}[curtain.position]
        fan_factor = {"low": 0.12, "medium": 0.20, "high": 0.30}
        fresh_factor = {"low": 0.08, "medium": 0.14, "high": 0.22}
        dehumidifier_factor = {"low": 0.18, "medium": 0.28, "high": 0.38}

        temperature_delta = (self._outdoor.outdoor_temp - room_state.temp) * (0.014 + window_exchange)
        sunlight_heat = max(0.0, self._outdoor.outdoor_brightness - 52) * 0.008 * natural_light_factor * sunlight_heat_factor
        temperature_delta += sunlight_heat

        if ac.power:
            fan_level_factor = {"low": 0.12, "medium": 0.18, "high": 0.24}.get(ac.fan_level, 0.16)
            if ac.mode == "cool":
                temperature_delta += (ac.target_temp - room_state.temp) * fan_level_factor
            elif ac.mode == "heat":
                temperature_delta += (ac.target_temp - room_state.temp) * fan_level_factor
            elif ac.mode == "dry":
                temperature_delta += (ac.target_temp + 0.5 - room_state.temp) * 0.10
            elif ac.mode == "fan":
                temperature_delta -= fan_level_factor * (0.6 + max(0.0, (room_state.humidity - 55) / 30.0))

        if fan.power:
            temperature_delta -= fan_factor.get(fan.speed, 0.12) * (1.0 + max(0.0, (room_state.humidity - 54) / 38.0))

        if fresh_air.power:
            temperature_delta += (self._outdoor.outdoor_temp - room_state.temp) * fresh_factor.get(fresh_air.flow_level, 0.08)

        if dehumidifier.power:
            temperature_delta += dehumidifier_factor.get(dehumidifier.level, 0.18) * 0.12

        if computer.power:
            activity_heat = {"idle": 0.06, "music": 0.12, "video": 0.20}.get(computer.activity, 0.08)
            temperature_delta += activity_heat

        if lighting.power:
            temperature_delta += (lighting.brightness / 100.0) * 0.04

        room_state.temp = round(self._clamp_float(room_state.temp + (temperature_delta * scale), 16.0, 35.0), 1)

        humidity_delta = (self._outdoor.outdoor_humidity - room_state.humidity) * (0.012 + (window_exchange * 0.55))
        if fresh_air.power:
            humidity_delta += (self._outdoor.outdoor_humidity - room_state.humidity) * fresh_factor.get(fresh_air.flow_level, 0.08) * 0.7
        if ac.power and ac.mode == "cool":
            humidity_delta -= 0.9
        if ac.power and ac.mode == "dry":
            humidity_delta -= 1.8
        if dehumidifier.power:
            humidity_delta += (dehumidifier.target_humidity - room_state.humidity) * dehumidifier_factor.get(dehumidifier.level, 0.18) * 0.16
        room_state.humidity = self._clamp_int(int(round(room_state.humidity + (humidity_delta * scale))), 25, 90)

        air_target = 56.0
        air_target += (self._outdoor.outdoor_air - 56.0) * window_exchange * 2.8
        if fresh_air.power:
            air_target += (self._outdoor.outdoor_air - 56.0) * (1.8 + (fresh_factor.get(fresh_air.flow_level, 0.08) * 4.0))
        if computer.power and computer.activity in {"music", "video"}:
            air_target -= 2.0
        if ac.power and ac.mode in {"cool", "heat"}:
            air_target -= 1.0
        room_state.air = self._clamp_int(
            int(round(self._approach(room_state.air, air_target, 0.20 * scale))),
            20,
            100,
        )

        natural_brightness = self._outdoor.outdoor_brightness * natural_light_factor * curtain_light_factor
        light_brightness = lighting.brightness * 0.88 if lighting.power else 0.0
        computer_brightness = 0.0
        if computer.power:
            glow_multiplier = {"idle": 0.18, "music": 0.10, "video": 0.34}.get(computer.activity, 0.16)
            computer_brightness = computer.screen_brightness * glow_multiplier
        brightness_target = 4.0 + natural_brightness + light_brightness + computer_brightness
        room_state.brightness = self._clamp_int(
            int(round(self._approach(room_state.brightness, brightness_target, 0.30 * scale))),
            0,
            100,
        )

        noise_target = 14.0 + (self._outdoor.outdoor_noise * window_noise)
        if ac.power:
            noise_target += {"low": 4.0, "medium": 6.0, "high": 9.0}.get(ac.fan_level, 5.0)
        if fan.power:
            noise_target += {"low": 3.5, "medium": 6.0, "high": 9.0}.get(fan.speed, 4.0)
        if fresh_air.power:
            noise_target += {"low": 3.0, "medium": 5.0, "high": 8.0}.get(fresh_air.flow_level, 4.0)
        if dehumidifier.power:
            noise_target += {"low": 4.0, "medium": 6.0, "high": 8.0}.get(dehumidifier.level, 5.0)
        if computer.power:
            base_noise = {"idle": 1.0, "music": 4.0, "video": 6.0}.get(computer.activity, 2.0)
            noise_target += base_noise + (computer.volume * 0.14)
        room_state.noise = self._clamp_int(
            int(round(self._approach(room_state.noise, noise_target, 0.28 * scale))),
            10,
            100,
        )

        energy_target = 3.0
        if ac.power:
            energy_target += {
                "cool": 22.0,
                "heat": 24.0,
                "dry": 16.0,
                "fan": 8.0,
                "off": 0.0,
            }.get(ac.mode, 12.0)
            energy_target += {"low": 2.0, "medium": 4.0, "high": 6.0}.get(ac.fan_level, 3.0)
            if fan.power and ac.mode in {"cool", "heat"}:
                energy_target -= 2.5
        if fan.power:
            energy_target += {"low": 3.0, "medium": 5.0, "high": 7.0}.get(fan.speed, 4.0)
        if fresh_air.power:
            energy_target += {"low": 5.0, "medium": 7.0, "high": 10.0}.get(fresh_air.flow_level, 6.0)
        if dehumidifier.power:
            energy_target += {"low": 6.0, "medium": 9.0, "high": 12.0}.get(dehumidifier.level, 7.0)
        if lighting.power:
            energy_target += max(2.0, lighting.brightness * 0.10)
        if computer.power:
            energy_target += {"idle": 6.0, "music": 10.0, "video": 15.0}.get(computer.activity, 8.0)
            energy_target += computer.screen_brightness * 0.05
        room_state.energy = self._clamp_int(
            int(round(self._approach(room_state.energy, energy_target, 0.24 * scale))),
            0,
            100,
        )

    def _refresh_meta(self) -> None:
        hour = self._current_time.hour + (self._current_time.minute / 60.0)
        self._meta.current_time = self._current_time.isoformat()
        if 5.0 <= hour < 8.0:
            self._meta.time_of_day = "dawn"
        elif 8.0 <= hour < 12.0:
            self._meta.time_of_day = "morning"
        elif 12.0 <= hour < 17.0:
            self._meta.time_of_day = "afternoon"
        elif 17.0 <= hour < 21.0:
            self._meta.time_of_day = "evening"
        else:
            self._meta.time_of_day = "night"

    def _push_event(self, message: str) -> None:
        timestamp = self._current_time.strftime("%H:%M")
        self._recent_events.insert(0, f"{timestamp} {message}")
        del self._recent_events[8:]

    @staticmethod
    def _approach(current: float, target: float, ratio: float) -> float:
        return current + ((target - current) * max(0.0, min(ratio, 1.0)))

    @staticmethod
    def _clamp_float(value: float, lower: float, upper: float) -> float:
        return max(lower, min(upper, value))

    @staticmethod
    def _clamp_int(value: int, lower: int, upper: int) -> int:
        return max(lower, min(upper, value))
