"""Baseline planners and framework comparison definitions."""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.environment.home_state import HomeState
from app.planning.action import PlannedAction
from app.planning.plan import ExecutionPlan


class FrameworkBaselineSpec(BaseModel):
    """One framework-level comparison target for experiments."""

    framework_id: str
    family: str
    reasoning_mode: str
    memory_mode: str
    coordination_mode: str
    description: str
    notes: list[str] = Field(default_factory=list)


class FusionDatasetBaselineSpec(BaseModel):
    """One runnable baseline for fusion-dataset evaluation."""

    baseline_id: str
    year: int
    display_name: str
    execution_mode: str
    principle: str
    characteristics: list[str] = Field(default_factory=list)
    primary_memory_backend: str = "none"
    llm_enabled: bool = False
    is_reference: bool = False


def build_framework_baseline_specs() -> list[FrameworkBaselineSpec]:
    """Return the recommended framework-level comparison set.

    The core comparison axis is framework design rather than model identity.
    When LLM-based frameworks are compared, they should ideally share the same
    underlying model so the results isolate the framework effect.
    """

    return [
        FrameworkBaselineSpec(
            framework_id="rule_only",
            family="rule_system",
            reasoning_mode="handwritten_rules",
            memory_mode="none",
            coordination_mode="single_pass",
            description="Pure rule-based controller without learned reasoning or memory retrieval.",
            notes=[
                "Lowest-cost control baseline.",
                "Useful lower bound for policy compliance and latency.",
            ],
        ),
        FrameworkBaselineSpec(
            framework_id="llm_direct",
            family="direct_llm",
            reasoning_mode="single_shot_generation",
            memory_mode="none",
            coordination_mode="none",
            description="One LLM directly maps task plus current sensors to final actions without explicit multi-agent discussion.",
            notes=[
                "Tests whether agent decomposition is needed at all.",
                "Should use the same model as other LLM-based frameworks.",
            ],
        ),
        FrameworkBaselineSpec(
            framework_id="agentic_no_memory",
            family="multi_agent_llm",
            reasoning_mode="agentic_discussion",
            memory_mode="none",
            coordination_mode="multi_agent_consensus",
            description="Current multi-agent orchestration with no retrieved long-term memory.",
            notes=[
                "Isolates the value of agent decomposition from memory support.",
            ],
        ),
        FrameworkBaselineSpec(
            framework_id="agentic_text_memory",
            family="multi_agent_llm",
            reasoning_mode="agentic_discussion",
            memory_mode="workspace_text",
            coordination_mode="multi_agent_consensus",
            description="Multi-agent framework with text snippets for initialization.",
            notes=[
                "Primary text-memory baseline against KG memory.",
            ],
        ),
        FrameworkBaselineSpec(
            framework_id="agentic_kg_memory",
            family="multi_agent_llm",
            reasoning_mode="agentic_discussion",
            memory_mode="kg_facts",
            coordination_mode="multi_agent_consensus",
            description="Multi-agent framework with graph-derived facts for initialization.",
            notes=[
                "Target framework for the main claim.",
            ],
        ),
        FrameworkBaselineSpec(
            framework_id="agentic_hybrid_memory",
            family="multi_agent_llm",
            reasoning_mode="agentic_discussion",
            memory_mode="hybrid",
            coordination_mode="multi_agent_consensus",
            description="Multi-agent framework combining graph facts and text memory.",
            notes=[
                "Useful ablation to test whether KG should replace or complement text memory.",
            ],
        ),
    ]


def build_fusion_dataset_baseline_specs() -> list[FusionDatasetBaselineSpec]:
    """Return runnable baselines aligned with the current fusion evaluation stack."""

    return [
        FusionDatasetBaselineSpec(
            baseline_id="rule_keyword",
            year=2025,
            display_name="Rule-Keyword Controller",
            execution_mode="rule_only",
            principle="Use lightweight keyword and sensor heuristics to directly map the task into a small action set.",
            characteristics=[
                "No discussion, no retrieval, almost no latency.",
                "Provides a conservative lower bound for action matching.",
                "Useful for checking whether MAS beats simple hand-written control logic.",
            ],
            primary_memory_backend="none",
            llm_enabled=False,
        ),
        FusionDatasetBaselineSpec(
            baseline_id="agentic_no_memory",
            year=2025,
            display_name="Agentic MAS Without Memory",
            execution_mode="dataset_runner",
            principle="Keep the current multi-agent discussion pipeline, but disable long-term memory retrieval entirely.",
            characteristics=[
                "Measures the contribution of agent decomposition alone.",
                "Strong baseline for wakeup, proposal, and final action metrics.",
                "Best control group before claiming memory brings gains.",
            ],
            primary_memory_backend="none",
            llm_enabled=False,
        ),
        FusionDatasetBaselineSpec(
            baseline_id="agentic_text_memory",
            year=2025,
            display_name="Agentic MAS With Workspace Text Memory",
            execution_mode="dataset_runner",
            principle="Use the same multi-agent orchestration, but retrieve textual workspace snippets instead of graph facts.",
            characteristics=[
                "Captures the value of lightweight narrative memory.",
                "A practical baseline against structured KG retrieval.",
                "Helps separate memory format gains from coordination gains.",
            ],
            primary_memory_backend="workspace_text",
            llm_enabled=False,
        ),
        FusionDatasetBaselineSpec(
            baseline_id="agentic_kg_memory",
            year=2025,
            display_name="Agentic MAS With KG Facts",
            execution_mode="dataset_runner",
            principle="Use graph-derived facts as the only long-term memory context during multi-agent discussion.",
            characteristics=[
                "Tests whether structured facts improve action grounding.",
                "Directly matches the repository's graph-memory design axis.",
                "Expected to help action precision and conflict-aware planning.",
            ],
            primary_memory_backend="kg_facts",
            llm_enabled=False,
        ),
        FusionDatasetBaselineSpec(
            baseline_id="agentic_hybrid_memory",
            year=2025,
            display_name="Agentic MAS With Hybrid Memory",
            execution_mode="dataset_runner",
            principle="Combine workspace text and graph facts in the same discussion pipeline.",
            characteristics=[
                "Strong reference system when both memory views are desired.",
                "Useful for checking whether graph memory complements rather than replaces text memory.",
                "Can act as the current best runnable reference for fusion evaluation.",
            ],
            primary_memory_backend="hybrid",
            llm_enabled=False,
            is_reference=True,
        ),
    ]


def build_keyword_baseline_selected_agents(description: str, home_state: HomeState) -> list[str]:
    """Infer a lightweight rule-based agent set from task text and sensors."""

    lowered = description.lower()
    selected: list[str] = []

    def include(agent_name: str) -> None:
        if agent_name not in selected:
            selected.append(agent_name)

    if any(keyword in lowered for keyword in ("cool", "hot", "warm", "temperature", "ac", "air conditioner")):
        include("cooling_agent")
    elif home_state.sensors.room_temperature_c >= 27:
        include("cooling_agent")

    if any(keyword in lowered for keyword in ("light", "bright", "brightness", "dim", "dark", "reading", "focus")):
        include("lighting_agent")
    elif home_state.sensors.ambient_light_level < 35:
        include("lighting_agent")

    if any(keyword in lowered for keyword in ("music", "speaker", "playlist", "tv", "television", "movie", "video")):
        include("music_agent")

    if any(keyword in lowered for keyword in ("fan", "breeze", "airflow", "circulation")):
        include("fan_agent")
    elif home_state.sensors.room_temperature_c >= 28 and "cooling_agent" not in selected:
        include("fan_agent")

    if any(keyword in lowered for keyword in ("curtain", "blind", "shade", "sunlight", "glare")):
        include("cover_agent")

    if any(keyword in lowered for keyword in ("lock", "unlock", "door", "security", "alarm")):
        include("lock_agent")

    if any(keyword in lowered for keyword in ("purifier", "humidifier", "fresh air", "air quality", "humidity")):
        include("switch_agent")

    if any(keyword in lowered for keyword in ("vacuum", "clean", "cleaning", "sweep", "robot")):
        include("appliance_agent")

    return selected


def build_keyword_baseline_plan(task_id: str, description: str, home_state: HomeState) -> ExecutionPlan:
    """A lightweight heuristic controller used as a runnable lower-bound baseline."""

    actions: list[PlannedAction] = []
    lowered = description.lower()

    if "cool" in lowered or home_state.sensors.room_temperature_c >= 27:
        actions.append(
            PlannedAction(
                device_id="living_room_ac_1",
                attribute="power",
                value=True,
                reason="Baseline cooling trigger",
                requested_by="keyword_baseline",
            )
        )
    elif "warm" in lowered or "heat" in lowered:
        actions.append(
            PlannedAction(
                device_id="living_room_ac_1",
                attribute="mode",
                value="heat",
                reason="Baseline heating trigger",
                requested_by="keyword_baseline",
            )
        )
    if "light" in lowered or home_state.sensors.ambient_light_level < 40:
        actions.append(
            PlannedAction(
                device_id="living_room_main",
                attribute="power",
                value=True,
                reason="Baseline lighting trigger",
                requested_by="keyword_baseline",
            )
        )
    if any(keyword in lowered for keyword in ("bright", "reading", "focus", "study")):
        actions.append(
            PlannedAction(
                device_id="living_room_main",
                attribute="brightness",
                value=75,
                reason="Baseline bright-scene trigger",
                requested_by="keyword_baseline",
            )
        )
    if any(keyword in lowered for keyword in ("dim", "movie", "video", "relax")):
        actions.append(
            PlannedAction(
                device_id="living_room_main",
                attribute="brightness",
                value=25,
                reason="Baseline dim-scene trigger",
                requested_by="keyword_baseline",
            )
        )
    if "music" in lowered and not home_state.sensors.quiet_hours:
        actions.append(
            PlannedAction(
                device_id="music_player",
                attribute="power",
                value=True,
                reason="Baseline music trigger",
                requested_by="keyword_baseline",
            )
        )
    if any(keyword in lowered for keyword in ("movie", "video", "tv", "television")) and not home_state.sensors.quiet_hours:
        actions.append(
            PlannedAction(
                device_id="music_player",
                attribute="input_source",
                value="tv",
                reason="Baseline media-scene trigger",
                requested_by="keyword_baseline",
            )
        )
    if any(keyword in lowered for keyword in ("fan", "breeze", "airflow", "circulation")):
        actions.append(
            PlannedAction(
                device_id="living_room_fan_1",
                attribute="power",
                value=True,
                reason="Baseline fan trigger",
                requested_by="keyword_baseline",
            )
        )
    if any(keyword in lowered for keyword in ("curtain", "blind", "shade")):
        actions.append(
            PlannedAction(
                device_id="living_room_curtain",
                attribute="position",
                value="closed" if any(token in lowered for token in ("close", "closed", "shade", "movie", "glare")) else "open",
                reason="Baseline cover trigger",
                requested_by="keyword_baseline",
            )
        )
    if any(keyword in lowered for keyword in ("lock", "security", "alarm")):
        actions.append(
            PlannedAction(
                device_id="front_door_lock",
                attribute="locked",
                value=True,
                reason="Baseline lock trigger",
                requested_by="keyword_baseline",
            )
        )
    if "unlock" in lowered:
        actions.append(
            PlannedAction(
                device_id="front_door_lock",
                attribute="locked",
                value=False,
                reason="Baseline unlock trigger",
                requested_by="keyword_baseline",
            )
        )
    if any(keyword in lowered for keyword in ("purifier", "fresh air", "air quality")):
        actions.append(
            PlannedAction(
                device_id="air_purifier",
                attribute="power",
                value=True,
                reason="Baseline purifier trigger",
                requested_by="keyword_baseline",
            )
        )
    if any(keyword in lowered for keyword in ("humidifier", "humidity", "humid")):
        actions.append(
            PlannedAction(
                device_id="bedroom_humidifier",
                attribute="power",
                value=True,
                reason="Baseline humidity trigger",
                requested_by="keyword_baseline",
            )
        )
    if any(keyword in lowered for keyword in ("vacuum", "clean", "cleaning", "sweep", "robot")):
        actions.append(
            PlannedAction(
                device_id="robot_vacuum_1",
                attribute="power",
                value=True,
                reason="Baseline cleaning trigger",
                requested_by="keyword_baseline",
            )
        )

    return ExecutionPlan(task_id=task_id, selected_actions=actions, rationale=["Keyword baseline plan"])
