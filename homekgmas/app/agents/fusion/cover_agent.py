"""Cover agent for curtains and blinds."""

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


class CoverAgent(BaseAgent):
    """Reason about privacy, sunlight, and scene enclosure."""

    def __init__(
        self,
        persona_name: str = "balanced",
        workspace_profile: AgentWorkspaceProfile | None = None,
        action_profile: AgentActionProfile | None = None,
        llm_client: ChatModelClient | None = None,
    ) -> None:
        descriptions = {
            "privacy-first": "Prioritizes enclosure and glare reduction.",
            "balanced": "Balances daylight, privacy, and scene needs.",
            "daylight-friendly": "Keeps covers open unless privacy or glare matters.",
        }
        super().__init__(
            name="cover_agent",
            persona=AgentPersona(
                name=persona_name,
                description=descriptions.get(persona_name, descriptions["balanced"]),
            ),
            workspace_profile=workspace_profile
            or AgentWorkspaceProfile(
                agent_name="cover_agent",
                workspace_dir=Path("."),
                soul="Shapes privacy and daylight so the room feels intentional and comfortable.",
                skills=[
                    "Curtain and blind positioning",
                    "Glare and privacy trade-off reasoning",
                ],
            ),
            capabilities=[
                Capability(name="cover_control", description="Opens and closes curtains or blinds."),
                Capability(name="scene_enclosure", description="Uses room context to choose cover positions."),
            ],
            action_profile=action_profile,
            llm_client=llm_client,
        )

    def allowed_action_targets(self) -> dict[str, set[str]]:
        return {
            "living_room_curtain": {"position"},
            "bedroom_blinds": {"position"},
        }

    def normalize_action_value(self, attribute: str, value):
        value = super().normalize_action_value(attribute, value)
        if attribute == "position":
            normalized = str(value).strip().lower()
            return normalized if normalized in {"open", "closed", "half"} else "half"
        return value

    def _build_action(self, device_id: str, position: str, reason: str) -> PlannedAction:
        return PlannedAction(
            device_id=device_id,
            attribute="position",
            value=position,
            reason=reason,
            requested_by=self.name,
        )

    def propose(self, topic: DiscussionTopic) -> AgentProposal:
        fallback_rationale = f"{self.persona.description} {self.memory_summary()}"
        llm_proposal = self.request_llm_proposal(
            topic=topic,
            round_index=1,
            domain_instructions=(
                "Focus on privacy, daylight, and scene enclosure. "
                "You control the living-room curtain and bedroom blinds."
            ),
            fallback_summary="Cover recommendation prepared from daylight and privacy cues.",
            fallback_rationale=fallback_rationale,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_propose(topic)

    def _rule_based_propose(self, topic: DiscussionTopic) -> AgentProposal:
        description = topic.description.lower()
        bedroom_task = "bedroom" in description or "wake" in description or "sleep" in description
        device_id = "bedroom_blinds" if bedroom_task else "living_room_curtain"
        if any(keyword in description for keyword in ("movie", "privacy", "secure", "away")):
            position = "closed"
        elif any(keyword in description for keyword in ("morning", "wake", "sunlight", "bright")):
            position = "open"
        elif self.persona.name == "privacy-first":
            position = "closed"
        elif self.persona.name == "daylight-friendly":
            position = "open"
        else:
            position = "half"

        actions = [self._build_action(device_id, position, f"{self.persona.name} cover positioning")] if (
            "curtain" in description
            or "blind" in description
            or "shade" in description
            or "movie" in description
            or "privacy" in description
            or "morning" in description
            or "wake" in description
        ) else []

        return AgentProposal(
            agent_name=self.name,
            summary="Cover recommendation prepared from daylight and privacy cues.",
            rationale=f"{self.persona.description} {self.memory_summary()}",
            round_index=1,
            actions=actions,
            concerns=["Closed covers may reduce natural light."] if actions and position == "closed" else [],
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
            domain_instructions="Revise your cover plan to balance privacy and visibility when conflicts mention either.",
            fallback_summary="Cover proposal revised after coordination feedback.",
            fallback_rationale="Adjusted cover position to better fit the shared scene.",
            prior_proposal=prior_proposal,
            revision_request=revision_request,
        )
        if llm_proposal is not None:
            return llm_proposal
        if not prior_proposal.actions:
            return prior_proposal.model_copy(update={"round_index": revision_request.round_index})

        descriptions = " ".join(conflict.description.lower() for conflict in revision_request.conflicts)
        actions = [action.model_copy(deep=True) for action in prior_proposal.actions]
        if "visibility" in descriptions or "brightness" in descriptions:
            for action in actions:
                action.value = "half"

        return AgentProposal(
            agent_name=self.name,
            summary="Cover proposal revised after coordination feedback.",
            rationale="Adjusted cover position to better fit the shared scene.",
            round_index=revision_request.round_index,
            actions=actions,
            concerns=["Cover position was softened after coordination feedback."],
        )
