"""Lock agent for entry security decisions."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.agents.fusion.base_agent import BaseAgent
from app.agents.catalog import AgentActionProfile
from app.agents.capability import Capability
from app.agents.persona import AgentPersona
from app.agents.fusion.workspace import AgentWorkspaceProfile
from app.discussion.protocol import AgentProposal, RevisionRequest
from app.llm.client import ChatModelClient
from app.orchestrator.topic_builder import DiscussionTopic
from app.planning.action import PlannedAction


class LockAgent(BaseAgent):
    """Reason about away mode and entry security."""

    def __init__(
        self,
        persona_name: str = "balanced",
        workspace_profile: AgentWorkspaceProfile | None = None,
        action_profile: AgentActionProfile | None = None,
        llm_client: ChatModelClient | None = None,
    ) -> None:
        descriptions = {
            "security-first": "Prioritizes locking quickly whenever away-mode cues appear.",
            "balanced": "Balances security with normal access convenience.",
            "presence-aware": "Avoids locking changes when occupancy suggests someone is active near the entry.",
        }
        super().__init__(
            name="lock_agent",
            persona=AgentPersona(
                name=persona_name,
                description=descriptions.get(persona_name, descriptions["balanced"]),
            ),
            workspace_profile=workspace_profile
            or AgentWorkspaceProfile(
                agent_name="lock_agent",
                workspace_dir=Path("."),
                soul="Keeps the home secure without making routine entry feel awkward.",
                skills=[
                    "Entry lock control",
                    "Away-mode and occupancy-aware security decisions",
                ],
            ),
            capabilities=[
                Capability(name="entry_lock_control", description="Locks or unlocks the front door."),
                Capability(name="security_reasoning", description="Uses task and occupancy context for secure entry decisions."),
            ],
            action_profile=action_profile,
            llm_client=llm_client,
        )

    def allowed_action_targets(self) -> dict[str, set[str]]:
        return {"front_door_lock": {"locked", "armed", "alarm_volume"}}

    def normalize_action_value(self, attribute: str, value: Any):
        value = super().normalize_action_value(attribute, value)
        if attribute == "alarm_volume":
            return max(0, min(100, int(value)))
        return value

    def propose(self, topic: DiscussionTopic) -> AgentProposal:
        fallback_rationale = f"{self.persona.description} {self.memory_summary()}"
        llm_proposal = self.request_llm_proposal(
            topic=topic,
            round_index=1,
            domain_instructions="Focus on securing or opening the entry lock based on occupancy and away-mode cues.",
            fallback_summary="Lock recommendation prepared from security and occupancy cues.",
            fallback_rationale=fallback_rationale,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_propose(topic)

    def _rule_based_propose(self, topic: DiscussionTopic) -> AgentProposal:
        description = topic.description.lower()
        living_room_occ = topic.sensor_snapshot.occupancy.get("living_room", False)
        bedroom_occ = topic.sensor_snapshot.occupancy.get("bedroom", False)
        away_like = any(keyword in description for keyword in ("away", "leave", "left home", "secure", "lock"))
        unlock_like = any(keyword in description for keyword in ("arrive", "welcome", "unlock", "open entry"))
        alarm_like = any(keyword in description for keyword in ("alarm", "armed", "security"))

        actions: list[PlannedAction] = []
        concerns: list[str] = []
        if away_like and (self.persona.name != "presence-aware" or not living_room_occ and not bedroom_occ):
            actions.append(
                PlannedAction(
                    device_id="front_door_lock",
                    attribute="locked",
                    value=True,
                    reason="Away-mode cues suggest securing the entry",
                    requested_by=self.name,
                    priority="high",
                )
            )
        elif unlock_like:
            actions.append(
                PlannedAction(
                    device_id="front_door_lock",
                    attribute="locked",
                    value=False,
                    reason="Task suggests the entry should be made accessible",
                    requested_by=self.name,
                    priority="high",
                )
            )
        elif away_like:
            concerns.append("Occupancy suggests someone may still be home, so locking was deferred")
        if alarm_like:
            actions.append(
                PlannedAction(
                    device_id="front_door_lock",
                    attribute="armed",
                    value=True,
                    reason="Security-like task suggests arming the alarm profile",
                    requested_by=self.name,
                    priority="medium",
                )
            )

        return AgentProposal(
            agent_name=self.name,
            summary="Lock recommendation prepared from security and occupancy cues.",
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
            domain_instructions="Revise your lock plan when conflicts mention occupancy, safety, or access convenience.",
            fallback_summary="Lock proposal revised after coordination feedback.",
            fallback_rationale="Adjusted lock timing to better align with shared context.",
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
                "summary": "Lock proposal revised after coordination feedback.",
                "rationale": ["Adjusted lock timing to better align with shared context."],
            }
        )
