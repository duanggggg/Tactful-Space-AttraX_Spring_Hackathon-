"""Memory schema models for local triples, memory records, and prompt contexts."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Triple(BaseModel):
    """A graph-like triple persisted locally."""

    subject: str
    predicate: str
    object: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryRecord(BaseModel):
    """A full task execution memory record."""

    record_id: str
    task_id: str
    created_at: str
    task_summary: str
    sensor_context: dict[str, Any] = Field(default_factory=dict)
    outdoor_context: dict[str, Any] = Field(default_factory=dict)
    device_context: dict[str, Any] = Field(default_factory=dict)
    involved_agents: list[str] = Field(default_factory=list)
    proposals: list[dict[str, Any]] = Field(default_factory=list)
    conflicts: list[dict[str, Any]] = Field(default_factory=list)
    final_actions: list[dict[str, Any]] = Field(default_factory=list)
    outcome: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    discussion_state: dict[str, Any] = Field(default_factory=dict)
    rounds_completed: int = 1
    triples: list[Triple] = Field(default_factory=list)


class MemoryQuery(BaseModel):
    """A simple local retrieval query."""

    agent_name: str | None = None
    keywords: list[str] = Field(default_factory=list)
    limit: int = 3


class GraphMemoryContext(BaseModel):
    """Compact graph-derived facts suitable for agent initialization."""

    backend: str = "kg_facts"
    facts: list[str] = Field(default_factory=list)
    reusable_strategies: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    source_record_ids: list[str] = Field(default_factory=list)
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)

    def has_content(self) -> bool:
        """Return True when the context has any useful content."""

        return bool(self.facts or self.reusable_strategies or self.warnings)

    def summary(self) -> str:
        """Return a compact one-line summary."""

        if not self.has_content():
            return "No matching graph memory yet."
        return (
            f"Loaded {len(self.facts)} graph fact(s), "
            f"{len(self.reusable_strategies)} reusable strategy note(s), and "
            f"{len(self.warnings)} warning(s)."
        )

    def render_for_prompt(self, *, max_chars: int = 700) -> str:
        """Render graph-derived context within a small prompt budget."""

        sections: list[str] = []
        if self.facts:
            sections.extend(f"- Fact: {fact}" for fact in self.facts)
        if self.reusable_strategies:
            sections.extend(f"- Strategy: {item}" for item in self.reusable_strategies)
        if self.warnings:
            sections.extend(f"- Warning: {item}" for item in self.warnings)
        return _pack_lines(sections, max_chars=max_chars)


def _pack_lines(lines: list[str], *, max_chars: int) -> str:
    """Pack short lines into a bounded prompt string."""

    if max_chars <= 0:
        return ""

    packed: list[str] = []
    total = 0
    for line in lines:
        cleaned = str(line).strip()
        if not cleaned:
            continue
        line_cost = len(cleaned) + (1 if packed else 0)
        if packed and total + line_cost > max_chars:
            break
        packed.append(cleaned)
        total += line_cost

    return "\n".join(packed)
