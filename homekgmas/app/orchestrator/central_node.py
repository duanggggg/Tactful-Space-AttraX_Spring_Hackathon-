"""Central orchestration node for the smart-home multi-agent scaffold."""

from __future__ import annotations

from pydantic import BaseModel

from app.agents.agent_registry import AgentRegistry
from app.api.schemas import TaskRequest
from app.core.utils import dedupe_preserve_order, utc_timestamp
from app.discussion.action_resolver import ActionResolver
from app.discussion.conflict_detector import ConflictDetector
from app.discussion.protocol import AgentDialogueEntry, CompressedDiscussionState
from app.environment.simulator import HomeSimulator
from app.memory.coordinator import MemoryCoordinator
from app.memory.dialogue_compressor import DialogueCompressor
from app.memory.memory_summarizer import MemorySummarizer
from app.memory.triple_store import TripleStore
from app.orchestrator.consensus_manager import ConsensusManager
from app.orchestrator.discussion_manager import DiscussionManager
from app.orchestrator.execution_planner import ExecutionPlanner
from app.orchestrator.topic_builder import TopicBuilder
from app.orchestrator.wakeup_manager import WakeupManager
from app.planning.plan import ExecutionPlan, ExecutionResult
from app.planning.validator import PlanValidator


class UserFacingResult(BaseModel):
    """A concise view intended for direct presentation to end users."""

    summary: str
    reasons: list[str]
    actions: list[str]
    success: bool
    scene_label: str


class OrchestrationResult(BaseModel):
    """Result returned after the central node handles one task."""

    task_id: str
    status: str
    user_view: UserFacingResult
    selected_agents: list[str]
    wakeup_scores: dict[str, int]
    agent_dialogue: list[AgentDialogueEntry]
    plan: ExecutionPlan
    conflicts: list[str]
    compression: CompressedDiscussionState
    execution: ExecutionResult
    memory_record_id: str
    created_at: str


class CentralNode:
    """Coordinates sensing, discussion, planning, execution, and memory persistence."""

    def __init__(
        self,
        simulator: HomeSimulator,
        agent_registry: AgentRegistry,
        triple_store: TripleStore,
        memory_coordinator: MemoryCoordinator,
        topic_builder: TopicBuilder,
        wakeup_manager: WakeupManager,
        discussion_manager: DiscussionManager,
        consensus_manager: ConsensusManager,
        execution_planner: ExecutionPlanner,
        plan_validator: PlanValidator,
        memory_summarizer: MemorySummarizer,
    ) -> None:
        self.simulator = simulator
        self.agent_registry = agent_registry
        self.triple_store = triple_store
        self.memory_coordinator = memory_coordinator
        self.topic_builder = topic_builder
        self.wakeup_manager = wakeup_manager
        self.discussion_manager = discussion_manager
        self.consensus_manager = consensus_manager
        self.execution_planner = execution_planner
        self.plan_validator = plan_validator
        self.memory_summarizer = memory_summarizer

    @classmethod
    def build_default(
        cls,
        simulator: HomeSimulator,
        agent_registry: AgentRegistry,
        triple_store: TripleStore,
        memory_coordinator: MemoryCoordinator,
        compression_window: int = 4,
    ) -> "CentralNode":
        compressor = DialogueCompressor(window_size=compression_window)
        conflict_detector = ConflictDetector()
        action_resolver = ActionResolver(catalog=agent_registry.catalog)
        return cls(
            simulator=simulator,
            agent_registry=agent_registry,
            triple_store=triple_store,
            memory_coordinator=memory_coordinator,
            topic_builder=TopicBuilder(),
            wakeup_manager=WakeupManager(),
            discussion_manager=DiscussionManager(
                compressor=compressor,
                conflict_detector=conflict_detector,
                action_resolver=action_resolver,
            ),
            consensus_manager=ConsensusManager(
                conflict_detector=conflict_detector,
                action_resolver=action_resolver,
                compressor=compressor,
            ),
            execution_planner=ExecutionPlanner(),
            plan_validator=PlanValidator(),
            memory_summarizer=MemorySummarizer(),
        )

    def handle_task(self, task: TaskRequest) -> OrchestrationResult:
        home_state = self.simulator.get_home_state()
        wakeup_scores = self.wakeup_manager.score_map(task, self.agent_registry)
        selected_agents = self.wakeup_manager.select_agents(task, self.agent_registry)

        memory_by_agent = {
            agent.name: self.memory_coordinator.retrieve_for_agent_with_context(
                agent.name,
                task.description,
                sensor_context=home_state.sensors.model_dump(mode="json"),
            )
            for agent in selected_agents
        }
        relevant_memory = [
            (
                f"{agent_name}: {len(bundle.graph_records)} graph record(s)"
                if bundle.active_backend == "triple_graph"
                else f"{agent_name}: {bundle.active_backend} active ({bundle.prompt_char_count()} prompt chars)"
            )
            for agent_name, bundle in memory_by_agent.items()
        ]

        topic = self.topic_builder.build(
            task_id=task.task_id,
            description=task.description,
            source=task.source,
            constraints=task.constraints,
            preferences=task.preferences,
            sensor_snapshot=home_state.sensors,
            outdoor_snapshot=home_state.outdoor,
            device_state=home_state.devices,
            relevant_memory=relevant_memory,
        )

        discussion_result = self.discussion_manager.run(
            topic=topic,
            agents=selected_agents,
            memory_by_agent=memory_by_agent,
            wakeup_scores=wakeup_scores,
        )
        plan, discussion_result = self.consensus_manager.build_plan(
            task_id=task.task_id,
            discussion_result=discussion_result,
            quiet_hours=home_state.sensors.quiet_hours,
            task_source=task.source,
            task_description=task.description,
            task_preferences=task.preferences,
            time_of_day=home_state.sensors.time_of_day,
            wakeup_scores=wakeup_scores,
        )
        plan = self.execution_planner.finalize(plan)

        validation = self.plan_validator.validate(plan)
        status = "accepted" if validation.valid else "needs_review"
        if not validation.valid:
            plan.conflicts.extend(validation.reasons)

        execution_result = self.simulator.execute(plan)
        memory_record = self.memory_summarizer.summarize(
            task_id=task.task_id,
            task_description=task.description,
            sensor_context=home_state.sensors.model_dump(mode="json"),
            outdoor_context=home_state.outdoor.model_dump(mode="json"),
            device_context=home_state.devices.model_dump(mode="json"),
            discussion_result=discussion_result,
            plan=plan,
            execution_result=execution_result,
        )
        self.triple_store.save_record(memory_record)
        self.memory_coordinator.persist_record(memory_record)

        return OrchestrationResult(
            task_id=task.task_id,
            status=status,
            user_view=self._build_user_view(home_state.sensors.time_of_day, home_state.sensors.quiet_hours, plan, execution_result),
            selected_agents=[agent.name for agent in selected_agents],
            wakeup_scores=wakeup_scores,
            agent_dialogue=self._build_agent_dialogue(discussion_result),
            plan=plan,
            conflicts=plan.conflicts,
            compression=discussion_result.compressed_state,
            execution=execution_result,
            memory_record_id=memory_record.record_id,
            created_at=utc_timestamp(),
        )

    def _build_agent_dialogue(self, discussion_result) -> list[AgentDialogueEntry]:
        """Convert proposal history into frontend-ready agent dialogue lines."""

        dialogue_entries: list[AgentDialogueEntry] = []

        for turn, proposal in zip(discussion_result.turns, discussion_result.proposal_history):
            dialogue_entries.append(
                AgentDialogueEntry(
                    round_index=turn.round_index,
                    agent_name=proposal.agent_name,
                    turn_type=turn.turn_type,
                    summary=proposal.summary,
                    rationale=proposal.rationale,
                    concerns=proposal.concerns,
                    validation_feedback=proposal.validation_feedback,
                    actions=proposal.actions,
                )
            )

        return dialogue_entries

    def _build_user_view(
        self,
        time_of_day: str,
        quiet_hours: bool,
        plan: ExecutionPlan,
        execution_result: ExecutionResult,
    ) -> UserFacingResult:
        scene_label = "Night mode" if quiet_hours else f"{time_of_day.replace('_', ' ').title()} scene"
        action_lines = [self._describe_action(action) for action in plan.selected_actions]
        if not action_lines:
            action_lines = ["No device changes were applied."]
        return UserFacingResult(
            summary=(
                f"Prepared a coordinated {scene_label.lower()} plan with "
                f"{len(plan.selected_actions)} selected device change(s)."
            ),
            reasons=dedupe_preserve_order(plan.rationale, limit=3),
            actions=action_lines,
            success=execution_result.success,
            scene_label=scene_label,
        )

    def _describe_action(self, action) -> str:
        if action.attribute == "brightness":
            return f"Set {action.device_id} brightness to {action.value}%."
        if action.attribute == "target_temperature":
            return f"Set {action.device_id} target temperature to {action.value} C."
        if action.attribute == "volume":
            return f"Set {action.device_id} volume to {action.value}."
        return f"Set {action.device_id}.{action.attribute} to {action.value}."
