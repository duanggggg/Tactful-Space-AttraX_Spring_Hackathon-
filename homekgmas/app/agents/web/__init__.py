"""Web-mode agent placeholders and workspace helpers."""

from app.agents.web.appliance_agent import ApplianceAgent
from app.agents.web.cooling_agent import CoolingAgent
from app.agents.web.cover_agent import CoverAgent
from app.agents.web.fan_agent import FanAgent
from app.agents.web.lighting_agent import LightingAgent
from app.agents.web.lock_agent import LockAgent
from app.agents.web.music_agent import MusicAgent
from app.agents.web.switch_agent import SwitchAgent
from app.agents.web.workspace import AgentWorkspaceProfile

__all__ = [
    "AgentWorkspaceProfile",
    "ApplianceAgent",
    "CoolingAgent",
    "CoverAgent",
    "FanAgent",
    "LightingAgent",
    "LockAgent",
    "MusicAgent",
    "SwitchAgent",
]
