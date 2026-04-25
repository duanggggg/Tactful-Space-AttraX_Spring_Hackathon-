"""Synthetic task helpers for local experiments."""

from __future__ import annotations

from itertools import cycle, islice

from app.api.schemas import TaskRequest


def build_demo_tasks() -> list[TaskRequest]:
    """Return a richer synthetic task set for local benchmarking."""

    return [
        TaskRequest(description="Create a cool calm evening with soft light and gentle music"),
        TaskRequest(description="Prepare a bright focused lighting scene for reading"),
        TaskRequest(description="Cool the living room without making the scene feel too active"),
        TaskRequest(description="Set up movie night with dim lights, closed curtains, and quiet cooling"),
        TaskRequest(description="Prepare the bedroom for sleep with a low fan and subtle lighting"),
        TaskRequest(description="Everyone has left home, secure the door and turn off unnecessary devices"),
        TaskRequest(description="The living room feels stuffy, run the purifier and improve air circulation"),
        TaskRequest(description="Open the bedroom blinds for a gentle wake-up routine and start calm music"),
        TaskRequest(description="Start the robot vacuum when the living room is empty"),
        TaskRequest(description="Make the bedroom more comfortable with humidity support and a quieter fan"),
    ]


def build_synthetic_tasks(sample_count: int = 16) -> list[TaskRequest]:
    """Repeat the benchmark templates until the requested sample count is reached."""

    templates = build_demo_tasks()
    if sample_count <= len(templates):
        return templates[:sample_count]
    return list(islice(cycle(templates), sample_count))
