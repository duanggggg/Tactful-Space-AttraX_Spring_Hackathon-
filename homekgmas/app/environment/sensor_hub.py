"""Sensor hub backed by local YAML defaults."""

from __future__ import annotations

from pathlib import Path

from app.core.config import load_yaml_file
from app.environment.home_state import SensorSnapshot


class SensorHub:
    """Reads the current sensor snapshot for the simulator."""

    def __init__(self, snapshot: SensorSnapshot | None = None) -> None:
        self._snapshot = snapshot or SensorSnapshot()

    @classmethod
    def from_config(cls, config_path: Path) -> "SensorHub":
        data = load_yaml_file(config_path)
        return cls(snapshot=SensorSnapshot(**data) if data else SensorSnapshot())

    def get_snapshot(self) -> SensorSnapshot:
        return self._snapshot.model_copy(deep=True)
