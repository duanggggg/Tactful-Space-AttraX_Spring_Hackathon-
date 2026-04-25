"""Workspace-based long-term and short-term memory persistence for agents."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from app.core.utils import dedupe_preserve_order, first_sentence, normalize_text_list
from app.memory.memory_schema import MemoryRecord
from app.storage.file_store import FileStore

if TYPE_CHECKING:
    from app.agents.fusion.workspace import AgentWorkspaceProfile


class WorkspaceMemoryContext(BaseModel):
    """Task-relevant workspace memory snippets for one agent."""

    backend: str = "workspace"
    short_term: list[str] = Field(default_factory=list)
    long_term: list[str] = Field(default_factory=list)

    def summary(self) -> str:
        """Return a one-line summary of loaded workspace memory."""

        if not self.short_term and not self.long_term:
            return "No matching workspace memory yet."
        return (
            f"Loaded {len(self.short_term)} short-term and "
            f"{len(self.long_term)} long-term workspace memory snippet(s)."
        )

    def has_content(self) -> bool:
        """Return True when any workspace snippet is available."""

        return bool(self.short_term or self.long_term)

    def render_for_prompt(self, *, max_chars: int = 700) -> str:
        """Render compact workspace snippets within a small prompt budget."""

        sections: list[str] = []
        sections.extend(f"- Recent: {item}" for item in self.short_term)
        sections.extend(f"- Durable: {item}" for item in self.long_term)
        packed: list[str] = []
        total = 0
        for line in sections:
            cleaned = str(line).strip()
            if not cleaned:
                continue
            line_cost = len(cleaned) + (1 if packed else 0)
            if packed and total + line_cost > max_chars:
                break
            packed.append(cleaned)
            total += line_cost
        return "\n".join(packed)


class WorkspaceMemoryStore:
    """Stores and retrieves agent-local workspace memory entries."""

    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.file_store = FileStore()
        self.file_store.ensure_dir(self.workspace_root)
        self._profiles: dict[str, AgentWorkspaceProfile] = {}

    def register_profile(self, profile: AgentWorkspaceProfile) -> None:
        """Register and bootstrap one agent workspace."""

        profile.ensure_structure(self.file_store)
        self._profiles[profile.agent_name] = profile

    def retrieve_for_agent(
        self,
        agent_name: str,
        task_text: str,
        *,
        short_term_limit: int = 3,
        long_term_limit: int = 3,
    ) -> WorkspaceMemoryContext:
        """Retrieve relevant workspace memory snippets for one task."""

        profile = self._profiles.get(agent_name)
        if profile is None:
            return WorkspaceMemoryContext()

        keywords = [token for token in task_text.lower().split() if len(token) > 3][:8]
        short_entries = self._top_entries(
            self.file_store.read_jsonl(profile.short_term_memory_path),
            keywords=keywords,
            limit=short_term_limit,
        )
        long_entries = self._top_entries(
            self.file_store.read_jsonl(profile.long_term_memory_path),
            keywords=keywords,
            limit=long_term_limit,
        )
        return WorkspaceMemoryContext(
            short_term=[entry["note"] for entry in short_entries],
            long_term=[entry["note"] for entry in long_entries],
        )

    def persist_record(self, record: MemoryRecord) -> None:
        """Write both short-term and long-term memory entries for involved agents."""

        proposal_map = {
            proposal.get("agent_name"): proposal
            for proposal in record.proposals
            if isinstance(proposal, dict) and proposal.get("agent_name")
        }
        for agent_name in record.involved_agents:
            profile = self._profiles.get(agent_name)
            if profile is None:
                continue

            proposal = proposal_map.get(agent_name, {})
            short_payload = {
                "created_at": record.created_at,
                "task_id": record.task_id,
                "task_summary": record.task_summary,
                "note": self._build_short_term_note(agent_name, record, proposal),
                "tags": record.tags,
            }
            long_payload = {
                "created_at": record.created_at,
                "task_id": record.task_id,
                "task_summary": record.task_summary,
                "note": self._build_long_term_note(agent_name, record, proposal),
                "tags": record.tags,
            }
            self.file_store.append_jsonl(profile.short_term_memory_path, short_payload)
            self.file_store.append_jsonl(profile.long_term_memory_path, long_payload)

    def _top_entries(
        self,
        entries: list[Any],
        *,
        keywords: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        scored: list[tuple[int, str, dict[str, Any]]] = []
        for raw in entries:
            if not isinstance(raw, dict):
                continue
            note = str(raw.get("note", "")).strip()
            if not note:
                continue
            haystack = f"{raw.get('task_summary', '')} {note} {json.dumps(raw.get('tags', []))}".lower()
            score = sum(2 for keyword in keywords if keyword in haystack)
            score += sum(1 for keyword in keywords if keyword in str(raw.get("task_summary", "")).lower())
            if score > 0 or not keywords:
                scored.append((score, str(raw.get("created_at", "")), raw))
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [entry for _, _, entry in scored[:limit]]

    def _build_short_term_note(
        self,
        agent_name: str,
        record: MemoryRecord,
        proposal: dict[str, Any],
    ) -> str:
        rationale = normalize_text_list(proposal.get("rationale"), max_items=2)
        concerns = normalize_text_list(proposal.get("concerns"), max_items=2)
        parts = [
            first_sentence(record.task_summary),
            f"{agent_name} recently considered {len(proposal.get('actions', []))} action(s).",
            *rationale,
            *concerns,
        ]
        return " ".join(part for part in parts if part)

    def _build_long_term_note(
        self,
        agent_name: str,
        record: MemoryRecord,
        proposal: dict[str, Any],
    ) -> str:
        action_descriptions = [
            f"{action.get('device_id')}.{action.get('attribute')}={action.get('value')}"
            for action in proposal.get("actions", [])
            if isinstance(action, dict)
        ]
        parts = [
            first_sentence(record.task_summary),
            f"{agent_name} durable pattern: {first_sentence(' '.join(normalize_text_list(proposal.get('rationale'), max_items=2)))}",
            (
                f"Typical actions: {', '.join(action_descriptions[:3])}."
                if action_descriptions
                else "Typical actions: none."
            ),
        ]
        return " ".join(part for part in parts if part)

    def list_profiles(self) -> list[str]:
        """Return registered agent names."""

        return list(self._profiles.keys())
