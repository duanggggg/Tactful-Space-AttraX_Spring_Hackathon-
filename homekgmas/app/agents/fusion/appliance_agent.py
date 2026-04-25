"""Appliance agent for robot vacuum and similar devices."""

from __future__ import annotations

from pathlib import Path

from app.agents.fusion.base_agent import BaseAgent
from app.agents.catalog import AgentActionProfile
from app.agents.capability import Capability
from app.agents.persona import AgentPersona
from app.agents.fusion.workspace import AgentWorkspaceProfile
from app.discussion.protocol import AgentProposal, RevisionRequest
from app.llm.client import ChatModelClient
from app.orchestrator.topic_builder import DiscussionTopic
from app.planning.action import PlannedAction


class ApplianceAgent(BaseAgent):
    """Reason about deferred appliance actions such as vacuum cleaning."""

    def __init__(
        self,
        persona_name: str = "balanced",
        workspace_profile: AgentWorkspaceProfile | None = None,
        action_profile: AgentActionProfile | None = None,
        llm_client: ChatModelClient | None = None,
    ) -> None:
        descriptions = {
            "proactive": "Starts small appliances readily when the context looks suitable.",
            "balanced": "Uses appliance actions when they fit the task and occupancy context.",
            "cautious": "Avoids appliance activity unless conditions are clearly suitable.",
        }
        super().__init__(
            name="appliance_agent",
            persona=AgentPersona(
                name=persona_name,
                description=descriptions.get(persona_name, descriptions["balanced"]),
            ),
            workspace_profile=workspace_profile
            or AgentWorkspaceProfile(
                agent_name="appliance_agent",
                workspace_dir=Path("."),
                soul="Runs helper appliances at the right time without disrupting occupants.",
                skills=[
                    "Robot vacuum scheduling",
                    "Occupancy-aware appliance activation",
                ],
            ),
            capabilities=[
                Capability(name="appliance_start_stop", description="Starts or stops simple appliance workflows."),
                Capability(name="occupancy_safe_automation", description="Uses occupancy and task cues to time appliance actions."),
            ],
            action_profile=action_profile,
            llm_client=llm_client,
        )

    def allowed_action_targets(self) -> dict[str, set[str]]:
        return {"robot_vacuum_1": {"power", "mode", "status"}}

    def normalize_action_value(self, attribute: str, value):
        value = super().normalize_action_value(attribute, value)
        if attribute == "mode":
            normalized = str(value).strip().lower()
            return normalized if normalized in {"clean", "quick", "dock"} else "clean"
        if attribute == "status":
            normalized = str(value).strip().lower()
            return normalized if normalized in {"idle", "cleaning", "docked"} else "idle"
        return value

    def propose(self, topic: DiscussionTopic) -> AgentProposal:
        fallback_rationale = f"{self.persona.description} {self.memory_summary()}"
        llm_proposal = self.request_llm_proposal(
            topic=topic,
            round_index=1,
            domain_instructions="Focus on timing appliance actions like robot vacuum runs based on occupancy and task intent.",
            fallback_summary="Appliance recommendation prepared from task and occupancy cues.",
            fallback_rationale=fallback_rationale,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_propose(topic)

    def _rule_based_propose(self, topic: DiscussionTopic) -> AgentProposal:
        description = topic.description.lower()
        living_room_occ = topic.sensor_snapshot.occupancy.get("living_room", False)
        cleaning_like = any(keyword in description for keyword in ("clean", "vacuum", "floor", "robot"))
        actions: list[PlannedAction] = []
        concerns: list[str] = []

        if cleaning_like and not living_room_occ:
            actions.extend(
                [
                    PlannedAction(
                        device_id="robot_vacuum_1",
                        attribute="power",
                        value=True,
                        reason="Cleaning task is appropriate while the room is unoccupied",
                        requested_by=self.name,
                        priority="medium",
                    ),
                    PlannedAction(
                        device_id="robot_vacuum_1",
                        attribute="mode",
                        value="quick" if self.persona.name != "proactive" else "clean",
                        reason=f"{self.persona.name} vacuum mode selection",
                        requested_by=self.name,
                    ),
                    PlannedAction(
                        device_id="robot_vacuum_1",
                        attribute="status",
                        value="cleaning",
                        reason="Vacuum should begin its cleaning pass now",
                        requested_by=self.name,
                    ),
                ]
            )
        elif cleaning_like:
            concerns.append("Vacuum action was deferred because the living room appears occupied")

        return AgentProposal(
            agent_name=self.name,
            summary="Appliance recommendation prepared from task and occupancy cues.",
            rationale=f"{self.persona.description} {self.memory_summary()}",
            round_index=1,
            actions=actions,
            concerns=concerns,
        )

    def revise(
        self,
        topic: DiscussionTopic,
        prior_proposal: AgentProposal,
        revision_request: RevisionRequest,
    ) -> AgentProposal:
        llm_proposal = self.request_llm_proposal(
            topic=topic,
            round_index=revision_request.round_index,
            domain_instructions="Revise appliance timing when conflicts mention occupancy, noise, or safety.",
            fallback_summary="Appliance proposal revised after coordination feedback.",
            fallback_rationale="Adjusted appliance timing to better fit the shared context.",
            prior_proposal=prior_proposal,
            revision_request=revision_request,
        )
        if llm_proposal is not None:
            return llm_proposal
        if not prior_proposal.actions:
            return prior_proposal.model_copy(update={"round_index": revision_request.round_index})
        return prior_proposal.model_copy(
            update={
                "round_index": revision_request.round_index,
                "summary": "Appliance proposal revised after coordination feedback.",
                "rationale": ["Adjusted appliance timing to better fit the shared context."],
            }
        )
