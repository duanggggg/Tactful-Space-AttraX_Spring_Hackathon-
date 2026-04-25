"""Factory helpers for fusion-mode agents and workspaces."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from app.agents.catalog import AgentCatalog
from app.agents.fusion.appliance_agent import ApplianceAgent
from app.agents.fusion.cooling_agent import CoolingAgent
from app.agents.fusion.cover_agent import CoverAgent
from app.agents.fusion.fan_agent import FanAgent
from app.agents.fusion.lighting_agent import LightingAgent
from app.agents.fusion.lock_agent import LockAgent
from app.agents.fusion.music_agent import MusicAgent
from app.agents.fusion.switch_agent import SwitchAgent
from app.agents.fusion.workspace import AgentWorkspaceProfile
from app.llm.client import ChatModelClient

AgentBuilder = Callable[[], object]


def build_workspace_profile(
    *,
    agent_name: str,
    agent_data: dict,
    workspace_root: Path,
) -> AgentWorkspaceProfile:
    """Build one fusion workspace profile rooted in the mode-specific workspace tree."""

    return AgentWorkspaceProfile(
        agent_name=agent_name,
        workspace_dir=workspace_root / agent_name,
        soul=str(agent_data.get("soul") or f"{agent_name} uses its configured domain judgment."),
        skills=[str(skill) for skill in agent_data.get("skills", [])],
    )


def build_agent_builders(
    *,
    data: dict,
    workspace_profiles: dict[str, AgentWorkspaceProfile],
    catalog: AgentCatalog,
    llm_client: ChatModelClient | None,
) -> dict[str, AgentBuilder]:
    """Return the fusion agent builders for the active runtime mode."""

    return {
        "cooling_agent": lambda: CoolingAgent(
            data.get("cooling_agent", {}).get("persona", "balanced"),
            workspace_profile=workspace_profiles["cooling_agent"],
            action_profile=catalog.profile_for("cooling_agent"),
            llm_client=llm_client,
        ),
        "lighting_agent": lambda: LightingAgent(
            data.get("lighting_agent", {}).get("persona", "balanced"),
            workspace_profile=workspace_profiles["lighting_agent"],
            action_profile=catalog.profile_for("lighting_agent"),
            llm_client=llm_client,
        ),
        "music_agent": lambda: MusicAgent(
            data.get("music_agent", {}).get("persona", "balanced"),
            workspace_profile=workspace_profiles["music_agent"],
            action_profile=catalog.profile_for("music_agent"),
            llm_client=llm_client,
        ),
        "fan_agent": lambda: FanAgent(
            data.get("fan_agent", {}).get("persona", "balanced"),
            workspace_profile=workspace_profiles["fan_agent"],
            action_profile=catalog.profile_for("fan_agent"),
            llm_client=llm_client,
        ),
        "cover_agent": lambda: CoverAgent(
            data.get("cover_agent", {}).get("persona", "balanced"),
            workspace_profile=workspace_profiles["cover_agent"],
            action_profile=catalog.profile_for("cover_agent"),
            llm_client=llm_client,
        ),
        "lock_agent": lambda: LockAgent(
            data.get("lock_agent", {}).get("persona", "balanced"),
            workspace_profile=workspace_profiles["lock_agent"],
            action_profile=catalog.profile_for("lock_agent"),
            llm_client=llm_client,
        ),
        "switch_agent": lambda: SwitchAgent(
            data.get("switch_agent", {}).get("persona", "balanced"),
            workspace_profile=workspace_profiles["switch_agent"],
            action_profile=catalog.profile_for("switch_agent"),
            llm_client=llm_client,
        ),
        "appliance_agent": lambda: ApplianceAgent(
            data.get("appliance_agent", {}).get("persona", "balanced"),
            workspace_profile=workspace_profiles["appliance_agent"],
            action_profile=catalog.profile_for("appliance_agent"),
            llm_client=llm_client,
        ),
    }
