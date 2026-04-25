"""Simple environment policy helpers."""

from __future__ import annotations

from app.environment.home_state import SensorSnapshot


def music_allowed(sensor_snapshot: SensorSnapshot) -> bool:
    """Return whether music playback is allowed in the current context."""

    return not sensor_snapshot.quiet_hours
