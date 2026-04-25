"""Web-mode workspace profile placeholder."""

from app.agents.fusion.workspace import AgentWorkspaceProfile as FusionAgentWorkspaceProfile


class AgentWorkspaceProfile(FusionAgentWorkspaceProfile):
    """Web-mode workspace profile.

    The storage layout is already split by file path. Web-specific workspace
    behavior can be added here later without touching the fusion tree.
    """

