"""Persona models for configurable agent behavior."""

from __future__ import annotations

from pydantic import BaseModel


class AgentPersona(BaseModel):
    """Represents an agent's configurable decision tendency."""

    name: str
    description: str
