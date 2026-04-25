"""Coordinate dual memory backends for retrieval and persistence."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.memory.graph_retriever import GraphRetriever
from app.memory.memory_schema import GraphMemoryContext, MemoryRecord
from app.memory.workspace_store import WorkspaceMemoryContext, WorkspaceMemoryStore


class AgentMemoryBundle(BaseModel):
    """Combined memory payload for one agent."""

    graph_records: list[MemoryRecord] = Field(default_factory=list)
    graph_context: GraphMemoryContext = Field(default_factory=GraphMemoryContext)
    workspace_context: WorkspaceMemoryContext = Field(default_factory=WorkspaceMemoryContext)
    active_backend: str = "triple_graph"

    def prompt_context(self, *, max_chars: int = 900) -> str:
        """Return the prompt-visible context for the active backend."""

        sections: list[str] = []
        if self.active_backend in {"kg_facts", "hybrid"} and self.graph_context.has_content():
            rendered = self.graph_context.render_for_prompt(max_chars=max_chars // 2 if self.active_backend == "hybrid" else max_chars)
            if rendered:
                sections.append(rendered)
        if self.active_backend in {"workspace_text", "workspace_dual", "hybrid"} and self.workspace_context.has_content():
            rendered = self.workspace_context.render_for_prompt(max_chars=max_chars // 2 if self.active_backend == "hybrid" else max_chars)
            if rendered:
                sections.append(rendered)
        if self.active_backend == "triple_graph" and self.graph_records:
            sections.extend(
                f"- Retrieved record: {record.task_summary}"
                for record in self.graph_records[:3]
            )
        return "\n".join(section for section in sections if section).strip()

    def prompt_char_count(self, *, max_chars: int = 900) -> int:
        """Estimate the prompt footprint of the memory bundle."""

        return len(self.prompt_context(max_chars=max_chars))


class MemoryCoordinator:
    """Owns both graph and workspace memory paths and selects the active one."""

    def __init__(
        self,
        *,
        graph_retriever: GraphRetriever,
        workspace_store: WorkspaceMemoryStore,
        primary_backend: str = "triple_graph",
    ) -> None:
        self.graph_retriever = graph_retriever
        self.workspace_store = workspace_store
        self.primary_backend = primary_backend

    def retrieve_for_agent(self, agent_name: str, task_text: str) -> AgentMemoryBundle:
        """Retrieve memory using the configured primary backend while keeping both available."""

        return self.retrieve_for_agent_with_context(agent_name, task_text, sensor_context=None)

    def retrieve_for_agent_with_context(
        self,
        agent_name: str,
        task_text: str,
        *,
        sensor_context: dict | None = None,
    ) -> AgentMemoryBundle:
        """Retrieve memory with optional sensor context for graph fact extraction."""

        if self.primary_backend == "none":
            return AgentMemoryBundle(
                graph_records=[],
                graph_context=GraphMemoryContext(),
                workspace_context=WorkspaceMemoryContext(),
                active_backend="none",
            )

        if self.primary_backend in {"workspace_dual", "workspace_text"}:
            workspace_context = self.workspace_store.retrieve_for_agent(agent_name, task_text)
            return AgentMemoryBundle(
                graph_records=[],
                graph_context=GraphMemoryContext(),
                workspace_context=workspace_context,
                active_backend="workspace_text",
            )

        graph_records = self.graph_retriever.retrieve_for_agent(agent_name, task_text)
        graph_context = self.graph_retriever.retrieve_context(
            agent_name,
            task_text,
            sensor_context=sensor_context,
        )
        if self.primary_backend == "kg_facts":
            return AgentMemoryBundle(
                graph_records=[],
                graph_context=graph_context,
                workspace_context=WorkspaceMemoryContext(),
                active_backend="kg_facts",
            )
        if self.primary_backend == "hybrid":
            workspace_context = self.workspace_store.retrieve_for_agent(agent_name, task_text)
            return AgentMemoryBundle(
                graph_records=[],
                graph_context=graph_context,
                workspace_context=workspace_context,
                active_backend="hybrid",
            )
        return AgentMemoryBundle(
            graph_records=graph_records,
            graph_context=GraphMemoryContext(),
            workspace_context=WorkspaceMemoryContext(),
            active_backend="triple_graph",
        )

    def persist_record(self, record: MemoryRecord) -> None:
        """Persist the workspace memory copy for later comparison."""

        self.workspace_store.persist_record(record)
