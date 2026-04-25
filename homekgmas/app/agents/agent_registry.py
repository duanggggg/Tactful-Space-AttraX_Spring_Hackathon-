"""Agent registry and configuration bootstrap."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable, Protocol

from app.agents.catalog import AgentCatalog, load_agent_catalog
from app.agents.fusion import factory as fusion_factory
from app.agents.web import factory as web_factory
from app.core.config import load_yaml_file
from app.core.constants import AGENT_NAMES
from app.llm.client import ChatModelClient
from app.memory.workspace_store import WorkspaceMemoryStore

if TYPE_CHECKING:
    from app.agents.fusion.workspace import AgentWorkspaceProfile


class AgentModeFactory(Protocol):
    """Protocol implemented by mode-specific agent factories."""

    def build_workspace_profile(
        self,
        *,
        agent_name: str,
        agent_data: dict,
        workspace_root: Path,
    ) -> AgentWorkspaceProfile:
        """Build one mode-specific workspace profile."""

    def build_agent_builders(
        self,
        *,
        data: dict,
        workspace_profiles: dict[str, AgentWorkspaceProfile],
        catalog: AgentCatalog,
        llm_client: ChatModelClient | None,
    ) -> dict[str, Callable[[], object]]:
        """Build the mode-specific agent constructors."""


class AgentRegistry:
    """Owns the configured domain-agent instances."""

    def __init__(self, agents: dict[str, object], catalog: AgentCatalog | None = None) -> None:
        self._agents = agents
        self.catalog = catalog or AgentCatalog(mode="generic", profiles={})

    @classmethod
    def from_config(
        cls,
        config_path: Path,
        workspace_store: WorkspaceMemoryStore,
        llm_client: ChatModelClient | None = None,
        *,
        agent_mode: str = "fusion",
        agent_catalog_path: Path | None = None,
    ) -> "AgentRegistry":
        data = load_yaml_file(config_path)
        catalog = load_agent_catalog(mode=agent_mode, catalog_path=agent_catalog_path)
        active_agent_names = cls._active_agent_names(catalog)
        mode_factory = cls._factory_for_mode(agent_mode)
        workspace_profiles = {
            agent_name: mode_factory.build_workspace_profile(
                agent_name=agent_name,
                agent_data=data.get(agent_name, {}),
                workspace_root=workspace_store.workspace_root,
            )
            for agent_name in active_agent_names
        }
        for profile in workspace_profiles.values():
            workspace_store.register_profile(profile)

        agent_builders = mode_factory.build_agent_builders(
            data=data,
            workspace_profiles=workspace_profiles,
            catalog=catalog,
            llm_client=llm_client,
        )
        agents = {agent_name: agent_builders[agent_name]() for agent_name in active_agent_names}
        return cls(agents, catalog=catalog)

    @staticmethod
    def _active_agent_names(catalog: AgentCatalog) -> tuple[str, ...]:
        """Return the ordered agent set enabled for the current mode."""

        metadata_agents = catalog.metadata.get("active_agents") if isinstance(catalog.metadata, dict) else None
        if isinstance(metadata_agents, list):
            names = tuple(agent_name for agent_name in AGENT_NAMES if agent_name in metadata_agents)
            if names:
                return names

        catalog_names = tuple(agent_name for agent_name in AGENT_NAMES if agent_name in catalog.profiles)
        if catalog_names:
            return catalog_names
        return AGENT_NAMES

    @staticmethod
    def _factory_for_mode(agent_mode: str) -> AgentModeFactory:
        """Return the mode-specific factory bundle for agents and workspaces."""

        if agent_mode == "web":
            return web_factory
        return fusion_factory

    def get(self, name: str):
        return self._agents[name]

    def list_agents(self) -> list:
        return list(self._agents.values())

    def profile_for(self, name: str):
        return self.catalog.profile_for(name)
