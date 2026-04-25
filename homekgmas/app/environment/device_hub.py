"""Device hub that owns mutable simulated device state."""

from __future__ import annotations

from pathlib import Path

from app.core.config import load_yaml_file
from app.environment.home_state import (
    AirConditionerState,
    ApplianceState,
    CoverState,
    DeviceState,
    FanState,
    LightState,
    LockState,
    MusicPlayerState,
    SwitchDeviceState,
)
from app.planning.action import PlannedAction


class DeviceHub:
    """Manages simulated device state changes."""

    def __init__(self, state: DeviceState | None = None) -> None:
        self._state = state or DeviceState()

    @classmethod
    def from_config(cls, config_path: Path) -> "DeviceHub":
        data = load_yaml_file(config_path)
        if not data:
            return cls()

        air_conditioners = {
            device_id: AirConditionerState(**payload)
            for device_id, payload in data.get("air_conditioners", {}).items()
        }
        lights = {
            device_id: LightState(**payload)
            for device_id, payload in data.get("lights", {}).items()
        }
        fans = {
            device_id: FanState(**payload)
            for device_id, payload in data.get("fans", {}).items()
        }
        covers = {
            device_id: CoverState(**payload)
            for device_id, payload in data.get("covers", {}).items()
        }
        locks = {
            device_id: LockState(**payload)
            for device_id, payload in data.get("locks", {}).items()
        }
        switches = {
            device_id: SwitchDeviceState(**payload)
            for device_id, payload in data.get("switches", {}).items()
        }
        appliances = {
            device_id: ApplianceState(**payload)
            for device_id, payload in data.get("appliances", {}).items()
        }
        music_player = MusicPlayerState(**data.get("music_player", {}))
        return cls(
            DeviceState(
                air_conditioners=air_conditioners,
                lights=lights,
                music_player=music_player,
                fans=fans,
                covers=covers,
                locks=locks,
                switches=switches,
                appliances=appliances,
            )
        )

    def get_state(self) -> DeviceState:
        return self._state.model_copy(deep=True)

    def apply_action(self, action: PlannedAction) -> None:
        if action.device_id in self._state.air_conditioners:
            setattr(self._state.air_conditioners[action.device_id], action.attribute, action.value)
            return
        if action.device_id in self._state.lights:
            setattr(self._state.lights[action.device_id], action.attribute, action.value)
            return
        if action.device_id == "music_player":
            setattr(self._state.music_player, action.attribute, action.value)
            return
        if action.device_id in self._state.fans:
            setattr(self._state.fans[action.device_id], action.attribute, action.value)
            return
        if action.device_id in self._state.covers:
            setattr(self._state.covers[action.device_id], action.attribute, action.value)
            return
        if action.device_id in self._state.locks:
            setattr(self._state.locks[action.device_id], action.attribute, action.value)
            return
        if action.device_id in self._state.switches:
            setattr(self._state.switches[action.device_id], action.attribute, action.value)
            return
        if action.device_id in self._state.appliances:
            setattr(self._state.appliances[action.device_id], action.attribute, action.value)
            return
        raise KeyError(f"Unknown device_id: {action.device_id}")
