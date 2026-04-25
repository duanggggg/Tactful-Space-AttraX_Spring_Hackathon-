"""Registry for dataset-source metadata without changing orchestration flow."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DatasetSourceProfile:
    """Describe one dataset source while keeping runtime flow unchanged."""

    source_dataset: str
    agent_mode: str
    source_family: str
    description: str = ""


DATASET_SOURCE_PROFILES: dict[str, DatasetSourceProfile] = {
    "home_assistant_datasets": DatasetSourceProfile(
        source_dataset="home_assistant_datasets",
        agent_mode="fusion",
        source_family="warehouse",
        description="Unified Home Assistant supervision source.",
    ),
    "smartsense": DatasetSourceProfile(
        source_dataset="smartsense",
        agent_mode="fusion",
        source_family="warehouse",
        description="Unified SmartSense supervision source.",
    ),
    "casas_zenodo": DatasetSourceProfile(
        source_dataset="casas_zenodo",
        agent_mode="fusion",
        source_family="warehouse",
        description="Unified CASAS environment-state source.",
    ),
    "edgewisepersona": DatasetSourceProfile(
        source_dataset="edgewisepersona",
        agent_mode="fusion",
        source_family="warehouse",
        description="Unified persona and routine source.",
    ),
    "zh_commands": DatasetSourceProfile(
        source_dataset="zh_commands",
        agent_mode="fusion",
        source_family="warehouse",
        description="Unified Chinese smart-home command source.",
    ),
    "web_ui": DatasetSourceProfile(
        source_dataset="web_ui",
        agent_mode="web",
        source_family="web",
        description="Web-collected browser interaction and state source.",
    ),
    "web_collected": DatasetSourceProfile(
        source_dataset="web_collected",
        agent_mode="web",
        source_family="web",
        description="External web dataset normalized into the same canonical structure.",
    ),
}


def get_dataset_source_profile(source_dataset: str) -> DatasetSourceProfile:
    """Return metadata for one dataset source, defaulting to a conservative profile."""

    normalized = str(source_dataset or "").strip() or "unknown"
    return DATASET_SOURCE_PROFILES.get(
        normalized,
        DatasetSourceProfile(
            source_dataset=normalized,
            agent_mode="fusion",
            source_family="unknown",
            description="Unknown source routed through the standard canonical pipeline.",
        ),
    )
