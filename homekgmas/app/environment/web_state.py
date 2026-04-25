"""State models for the standalone web simulator."""

from __future__ import annotations

from pydantic import BaseModel, Field


class WebMetaState(BaseModel):
    """Simulation time metadata."""

    current_time: str = "2026-04-10T18:00:00+08:00"
    time_of_day: str = "evening"


class WebOutdoorState(BaseModel):
    """Outdoor conditions visible to the web simulator."""

    weather: str = "clear"
    outdoor_temp: float = 30.0
    outdoor_humidity: int = 68
    outdoor_air: int = 72
    outdoor_noise: int = 30
    outdoor_brightness: int = 76


class RoomClimateState(BaseModel):
    """One room's web-visible environment."""

    temp: float = 27.0
    humidity: int = 58
    air: int = 62
    noise: int = 24
    brightness: int = 34
    energy: int = 8


class WebIndoorState(BaseModel):
    """Indoor environment for the living room and bedroom."""

    living: RoomClimateState = Field(
        default_factory=lambda: RoomClimateState(
            temp=27.6,
            humidity=60,
            air=60,
            noise=25,
            brightness=38,
            energy=9,
        )
    )
    bedroom: RoomClimateState = Field(
        default_factory=lambda: RoomClimateState(
            temp=26.4,
            humidity=57,
            air=64,
            noise=20,
            brightness=24,
            energy=6,
        )
    )


class AirConditionerUnitState(BaseModel):
    power: bool = False
    mode: str = "off"
    target_temp: int = 26
    fan_level: str = "medium"


class WindowUnitState(BaseModel):
    position: str = "closed"


class CurtainUnitState(BaseModel):
    position: str = "half"


class FanUnitState(BaseModel):
    power: bool = False
    speed: str = "low"


class FreshAirUnitState(BaseModel):
    power: bool = False
    flow_level: str = "low"


class DehumidifierUnitState(BaseModel):
    power: bool = False
    target_humidity: int = 50
    level: str = "medium"


class LightingUnitState(BaseModel):
    power: bool = False
    brightness: int = 0
    scene: str = "off"


class ComputerUnitState(BaseModel):
    power: bool = False
    activity: str = "idle"
    volume: int = 0
    screen_brightness: int = 0


class ZonedPairState(BaseModel):
    """Base container for paired room states."""


class ZonedAirConditionerState(ZonedPairState):
    living: AirConditionerUnitState = Field(default_factory=AirConditionerUnitState)
    bedroom: AirConditionerUnitState = Field(default_factory=AirConditionerUnitState)


class ZonedWindowState(ZonedPairState):
    living: WindowUnitState = Field(default_factory=WindowUnitState)
    bedroom: WindowUnitState = Field(default_factory=WindowUnitState)


class ZonedCurtainState(ZonedPairState):
    living: CurtainUnitState = Field(default_factory=CurtainUnitState)
    bedroom: CurtainUnitState = Field(default_factory=CurtainUnitState)


class ZonedFanState(ZonedPairState):
    living: FanUnitState = Field(default_factory=FanUnitState)
    bedroom: FanUnitState = Field(default_factory=FanUnitState)


class ZonedFreshAirState(ZonedPairState):
    living: FreshAirUnitState = Field(default_factory=FreshAirUnitState)
    bedroom: FreshAirUnitState = Field(default_factory=FreshAirUnitState)


class ZonedDehumidifierState(ZonedPairState):
    living: DehumidifierUnitState = Field(default_factory=DehumidifierUnitState)
    bedroom: DehumidifierUnitState = Field(default_factory=DehumidifierUnitState)


class ZonedLightingState(ZonedPairState):
    living: LightingUnitState = Field(default_factory=LightingUnitState)
    bedroom: LightingUnitState = Field(default_factory=LightingUnitState)


class ZonedComputerState(ZonedPairState):
    living: ComputerUnitState = Field(default_factory=ComputerUnitState)
    bedroom: ComputerUnitState = Field(default_factory=ComputerUnitState)


class WebAgentState(BaseModel):
    """All web-agent states that can be manipulated from the UI."""

    air_conditioner: ZonedAirConditionerState = Field(default_factory=ZonedAirConditionerState)
    window: ZonedWindowState = Field(default_factory=ZonedWindowState)
    curtain: ZonedCurtainState = Field(default_factory=ZonedCurtainState)
    fan: ZonedFanState = Field(default_factory=ZonedFanState)
    fresh_air: ZonedFreshAirState = Field(default_factory=ZonedFreshAirState)
    dehumidifier: ZonedDehumidifierState = Field(default_factory=ZonedDehumidifierState)
    lighting: ZonedLightingState = Field(default_factory=ZonedLightingState)
    computer: ZonedComputerState = Field(default_factory=ZonedComputerState)


class WebSimulatorSnapshot(BaseModel):
    """Combined payload rendered by the standalone web simulator."""

    meta: WebMetaState
    outdoor: WebOutdoorState
    indoor: WebIndoorState
    agents: WebAgentState
    recent_events: list[str] = Field(default_factory=list)
