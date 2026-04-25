import json

from app.agents.agent_registry import AgentRegistry
from app.core.config import build_settings
from app.memory.workspace_store import WorkspaceMemoryStore


def test_build_settings_uses_explicit_fusion_workspace_dir(tmp_path):
    settings = build_settings({"output_dir": tmp_path / "outputs"})

    assert settings.agent_workspace_dir == tmp_path / "outputs" / "agent_workspaces" / "fusion"


def test_build_settings_uses_mode_specific_web_defaults(tmp_path):
    settings = build_settings({"output_dir": tmp_path / "outputs", "agent_mode": "web"})

    assert settings.agents_config_path.name == "agents_web.yaml"
    assert settings.agent_catalog_path.name == "web_agent_catalog.json"
    assert settings.memory_dir == tmp_path / "outputs" / "memory" / "web"
    assert settings.log_dir == tmp_path / "outputs" / "logs" / "web"
    assert settings.report_dir == tmp_path / "outputs" / "reports" / "web"
    assert settings.agent_workspace_dir == tmp_path / "outputs" / "agent_workspaces" / "web"


def test_agent_registry_respects_catalog_active_agents(tmp_path):
    catalog_path = tmp_path / "web_catalog.json"
    catalog_path.write_text(
        json.dumps(
            {
                "mode": "web",
                "metadata": {"active_agents": ["lighting_agent"]},
                "profiles": {
                    "lighting_agent": {
                        "agent_name": "lighting_agent",
                        "mode": "web",
                        "allowed_devices": {"living_room_main": ["power", "brightness"]},
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    settings = build_settings(
        {
            "output_dir": tmp_path / "outputs",
            "agent_mode": "web",
            "agent_catalog_path": catalog_path,
        }
    )
    workspace_store = WorkspaceMemoryStore(settings.agent_workspace_dir)
    registry = AgentRegistry.from_config(
        settings.agents_config_path,
        workspace_store=workspace_store,
        agent_mode=settings.agent_mode,
        agent_catalog_path=settings.agent_catalog_path,
    )

    assert [agent.name for agent in registry.list_agents()] == ["lighting_agent"]
    assert registry.get("lighting_agent").__class__.__module__.startswith("app.agents.web.")
