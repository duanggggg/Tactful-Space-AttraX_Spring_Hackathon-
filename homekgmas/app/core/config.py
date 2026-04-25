"""Application settings and lightweight config loading."""

from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator
import yaml

from app.storage.paths import CONFIGS_DIR, OUTPUTS_DIR, PROJECT_ROOT


def default_agents_config_path_for_mode(agent_mode: str) -> Path:
    """Return the mode-specific default agent config path."""

    if agent_mode == "web":
        return CONFIGS_DIR / "agents_web.yaml"
    return CONFIGS_DIR / "agents.yaml"


def default_agent_catalog_path_for_mode(agent_mode: str) -> Path | None:
    """Return the mode-specific default catalog path."""

    if agent_mode == "fusion":
        return PROJECT_ROOT / "metadata" / "fusion_agent_catalog.json"
    if agent_mode == "web":
        return PROJECT_ROOT / "metadata" / "web_agent_catalog.json"
    return None


class AppSettings(BaseModel):
    """Runtime settings for the local MVP scaffold."""

    project_name: str = "homekgmas"
    api_prefix: str = "/api/v1"
    output_dir: Path = OUTPUTS_DIR
    memory_dir: Path | None = None
    agent_workspace_dir: Path | None = None
    log_dir: Path | None = None
    report_dir: Path | None = None
    compression_window: int = 4
    memory_top_k: int = 3
    primary_memory_backend: Literal[
        "triple_graph",
        "workspace_dual",
        "workspace_text",
        "kg_facts",
        "hybrid",
        "none",
    ] = "triple_graph"
    agent_mode: Literal["generic", "fusion", "web"] = "fusion"
    system_config_path: Path = CONFIGS_DIR / "system.yaml"
    agents_config_path: Path | None = None
    agent_catalog_path: Path | None = None
    sensors_config_path: Path = CONFIGS_DIR / "sensors.yaml"
    devices_config_path: Path = CONFIGS_DIR / "devices.yaml"
    simulator_config_path: Path = CONFIGS_DIR / "simulator.yaml"
    simulator_mode: Literal["embedded", "remote"] = "embedded"
    simulator_api_base: str = "http://127.0.0.1:8011"
    simulator_request_timeout_seconds: float = 5.0
    llm_enabled: bool = False
    openai_api_key: str | None = None
    openai_api_base: str | None = None
    openai_model: str | None = None
    openai_timeout_seconds: float = 30.0
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def populate_paths(self) -> "AppSettings":
        """Derive output subdirectories when not supplied explicitly."""

        self.output_dir = self._resolve_path(self.output_dir)
        self.system_config_path = self._resolve_path(self.system_config_path)
        if self.agents_config_path is None:
            self.agents_config_path = default_agents_config_path_for_mode(self.agent_mode)
        if self.agent_catalog_path is None:
            self.agent_catalog_path = default_agent_catalog_path_for_mode(self.agent_mode)
        self.agents_config_path = self._resolve_path(self.agents_config_path)
        self.agent_catalog_path = self._resolve_path(self.agent_catalog_path)
        self.sensors_config_path = self._resolve_path(self.sensors_config_path)
        self.devices_config_path = self._resolve_path(self.devices_config_path)
        self.simulator_config_path = self._resolve_path(self.simulator_config_path)

        if self.memory_dir is None:
            self.memory_dir = self.output_dir / "memory" if self.agent_mode == "fusion" else self.output_dir / "memory" / self.agent_mode
        if self.log_dir is None:
            self.log_dir = self.output_dir / "logs" if self.agent_mode == "fusion" else self.output_dir / "logs" / self.agent_mode
        if self.report_dir is None:
            self.report_dir = self.output_dir / "reports" if self.agent_mode == "fusion" else self.output_dir / "reports" / self.agent_mode
        if self.agent_workspace_dir is None:
            self.agent_workspace_dir = self.output_dir / "agent_workspaces" / self.agent_mode
        if (
            not self.llm_enabled
            and self.openai_api_key
            and self.openai_api_base
            and self.openai_model
        ):
            self.llm_enabled = True

        self.memory_dir = self._resolve_path(self.memory_dir)
        self.log_dir = self._resolve_path(self.log_dir)
        self.report_dir = self._resolve_path(self.report_dir)
        self.agent_workspace_dir = self._resolve_path(self.agent_workspace_dir)
        return self

    @staticmethod
    def _resolve_path(path: Path | None) -> Path | None:
        """Resolve repo-relative paths into stable absolute paths."""

        if path is None:
            return None
        candidate = Path(path)
        if candidate.is_absolute():
            return candidate
        return PROJECT_ROOT / candidate

    def ensure_directories(self) -> None:
        """Create output directories required by the app."""

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        self.agent_workspace_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)


def load_yaml_file(path: Path) -> dict[str, Any]:
    """Read a YAML file if it exists, otherwise return an empty mapping."""

    if not path.exists():
        return {}
    with path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        return {}
    return payload


def load_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=VALUE pairs from a local .env-style file."""

    if not path.exists():
        return {}

    env_data: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if value and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            env_data[key] = value

    return env_data


def parse_bool(value: str) -> bool:
    """Parse common truthy strings into a boolean."""

    return value.strip().lower() in {"1", "true", "yes", "on"}


def build_settings(overrides: dict[str, Any] | None = None) -> AppSettings:
    """Build settings from YAML defaults, environment overrides, and explicit overrides."""

    config_data = load_yaml_file(CONFIGS_DIR / "system.yaml")
    dotenv_data = load_env_file(PROJECT_ROOT / ".env")
    env_data: dict[str, Any] = {}

    def read_env(name: str) -> str | None:
        return os.getenv(name, dotenv_data.get(name))

    output_dir = read_env("HOMEKG_OUTPUT_DIR")
    if output_dir:
        env_data["output_dir"] = Path(output_dir)
    llm_enabled = read_env("HOMEKG_LLM_ENABLED")
    if llm_enabled is not None:
        env_data["llm_enabled"] = parse_bool(llm_enabled)
    openai_api_key = read_env("OPENAI_API_KEY")
    if openai_api_key:
        env_data["openai_api_key"] = openai_api_key
    openai_api_base = read_env("OPENAI_API_BASE")
    if openai_api_base:
        env_data["openai_api_base"] = openai_api_base
    openai_model = read_env("OPENAI_MODEL")
    if openai_model:
        env_data["openai_model"] = openai_model
    openai_timeout = read_env("OPENAI_TIMEOUT_SECONDS")
    if openai_timeout:
        env_data["openai_timeout_seconds"] = float(openai_timeout)
    simulator_mode = read_env("HOMEKG_SIMULATOR_MODE")
    if simulator_mode:
        env_data["simulator_mode"] = simulator_mode
    simulator_api_base = read_env("HOMEKG_SIMULATOR_API_BASE")
    if simulator_api_base:
        env_data["simulator_api_base"] = simulator_api_base
    simulator_timeout = read_env("HOMEKG_SIMULATOR_TIMEOUT_SECONDS")
    if simulator_timeout:
        env_data["simulator_request_timeout_seconds"] = float(simulator_timeout)
    primary_memory_backend = read_env("HOMEKG_PRIMARY_MEMORY_BACKEND")
    if primary_memory_backend:
        env_data["primary_memory_backend"] = primary_memory_backend
    agent_mode = read_env("HOMEKG_AGENT_MODE")
    if agent_mode:
        env_data["agent_mode"] = agent_mode
    agent_catalog_path = read_env("HOMEKG_AGENT_CATALOG_PATH")
    if agent_catalog_path:
        env_data["agent_catalog_path"] = Path(agent_catalog_path)
    workspace_dir = read_env("HOMEKG_AGENT_WORKSPACE_DIR")
    if workspace_dir:
        env_data["agent_workspace_dir"] = Path(workspace_dir)

    merged_config = {**config_data, **env_data, **(overrides or {})}
    settings = AppSettings(**merged_config)
    settings.ensure_directories()
    return settings


@lru_cache
def get_settings() -> AppSettings:
    """Return cached process settings."""

    return build_settings()
