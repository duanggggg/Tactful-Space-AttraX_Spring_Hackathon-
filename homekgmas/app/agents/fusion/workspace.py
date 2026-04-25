"""Agent workspace profiles inspired by OpenClaw-style agent folders."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.storage.file_store import FileStore


@dataclass
class AgentWorkspaceProfile:
    """Represents one agent's dedicated local workspace."""

    agent_name: str
    workspace_dir: Path
    soul: str
    skills: list[str]

    @property
    def soul_path(self) -> Path:
        return self.workspace_dir / "SOUL.md"

    @property
    def skills_path(self) -> Path:
        return self.workspace_dir / "SKILLS.md"

    @property
    def memory_overview_path(self) -> Path:
        return self.workspace_dir / "MEMORY.md"

    @property
    def short_term_memory_path(self) -> Path:
        return self.workspace_dir / "memory" / "short_term.jsonl"

    @property
    def long_term_memory_path(self) -> Path:
        return self.workspace_dir / "memory" / "long_term.jsonl"

    def ensure_structure(self, file_store: FileStore | None = None) -> None:
        """Create the expected workspace files when missing."""

        store = file_store or FileStore()
        store.ensure_dir(self.workspace_dir / "memory")

        if not self.soul_path.exists():
            store.write_text(
                self.soul_path,
                f"# {self.agent_name} Soul\n\n{self.soul.strip()}\n",
            )
        if not self.skills_path.exists():
            skills_body = "\n".join(f"- {skill}" for skill in self.skills) or "- No explicit skills configured"
            store.write_text(
                self.skills_path,
                f"# {self.agent_name} Skills\n\n{skills_body}\n",
            )
        if not self.memory_overview_path.exists():
            store.write_text(
                self.memory_overview_path,
                (
                    f"# {self.agent_name} Memory\n\n"
                    "This workspace stores two local memory streams for comparison work:\n\n"
                    "- `short_term.jsonl` for recent task-level notes\n"
                    "- `long_term.jsonl` for condensed durable summaries\n\n"
                    "The default runtime retrieval path still prefers triple-store / graph memory unless configured otherwise.\n"
                ),
            )
        if not self.short_term_memory_path.exists():
            store.write_text(self.short_term_memory_path, "")
        if not self.long_term_memory_path.exists():
            store.write_text(self.long_term_memory_path, "")

    def soul_summary(self) -> str:
        """Return a concise soul string suitable for prompts."""

        return self.soul.strip()

    def skills_summary(self) -> str:
        """Return a concise skills string suitable for prompts."""

        return ", ".join(skill.strip() for skill in self.skills if skill.strip())
