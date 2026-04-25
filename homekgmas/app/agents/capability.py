"""Capability metadata for domain agents."""

from __future__ import annotations

from pydantic import BaseModel


class Capability(BaseModel):
    """A simple agent capability descriptor."""

    name: str
    description: str
