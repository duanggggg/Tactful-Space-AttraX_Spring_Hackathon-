"""Fan agent for air-circulation recommendations."""

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


class FanAgent(BaseAgent):
    """Reason about airflow, comfort, and low-noise circulation."""

    def __init__(
        self,
        persona_name: str = "balanced",
        workspace_profile: AgentWorkspaceProfile | None = None,
        action_profile: AgentActionProfile | None = None,
        llm_client: ChatModelClient | None = None,
    ) -> None:
        descriptions = {
            "quiet-comfort": "Prefers gentle air circulation with minimal noise.",
            "balanced": "Balances circulation, comfort, and noise.",
            "cooling-boost": "Uses stronger airflow when cooling support is needed.",
        }
        super().__init__(
            name="fan_agent",
            persona=AgentPersona(
                name=persona_name,
                description=descriptions.get(persona_name, descriptions["balanced"]),
            ),
            workspace_profile=workspace_profile
            or AgentWorkspaceProfile(
                agent_name="fan_agent",
                workspace_dir=Path("."),
                soul="Keeps air moving in a calm, quiet way that supports comfort scenes.",
                skills=[
                    "Bedroom and living-room fan control",
                    "Noise-aware airflow adjustments",
                ],
            ),
            capabilities=[
                Capability(
                    name="fan_power_control",
                    description="Controls power and speed for circulation fans.",
                ),
                Capability(
                    name="comfort_circulation",
                    description="Uses temperature, occupancy, and task tone to set airflow.",
                ),
            ],
            action_profile=action_profile,
            llm_client=llm_client,
        )

    def allowed_action_targets(self) -> dict[str, set[str]]:
        return {
            "living_room_fan_1": {"power", "speed", "oscillate"},
            "bedroom_fan_1": {"power", "speed", "oscillate"},
        }

    def normalize_action_value(self, attribute: str, value: Any) -> Any:
        value = super().normalize_action_value(attribute, value)
        if attribute == "speed":
            normalized = str(value).strip().lower()
            return normalized if normalized in {"low", "medium", "high"} else "medium"
        return value

    def _build_actions(self, device_id: str, speed: str, oscillate: bool) -> list[PlannedAction]:
        return [
            PlannedAction(
                device_id=device_id,
                attribute="power",
                value=True,
                reason="Air circulation would improve current comfort",
                requested_by=self.name,
            ),
            PlannedAction(
                device_id=device_id,
                attribute="speed",
                value=speed,
                reason=f"{self.persona.name} fan speed selection",
                requested_by=self.name,
            ),
            PlannedAction(
                device_id=device_id,
                attribute="oscillate",
                value=oscillate,
                reason="Oscillation helps distribute airflow more evenly",
                requested_by=self.name,
                priority="low",
            ),
        ]

    def propose(self, topic: DiscussionTopic) -> AgentProposal:
        fallback_rationale = f"{self.persona.description} {self.memory_summary()}"
        llm_proposal = self.request_llm_proposal(
            topic=topic,
            round_index=1,
            domain_instructions=(
                "Focus on airflow, temperature support, and noise trade-offs. "
                "You control only the living-room and bedroom fans."
            ),
            fallback_summary="Fan recommendation prepared from comfort and circulation cues.",
            fallback_rationale=fallback_rationale,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_propose(topic)

    def _rule_based_propose(self, topic: DiscussionTopic) -> AgentProposal:
        description = topic.description.lower()
        room = "bedroom" if "bedroom" in description or "sleep" in description else "living_room"
        device_id = "bedroom_fan_1" if room == "bedroom" else "living_room_fan_1"
        room_temp = (
            topic.sensor_snapshot.bedroom_temperature_c
            if room == "bedroom"
            else topic.sensor_snapshot.room_temperature_c
        )
        wants_fan = any(keyword in description for keyword in ("fan", "breeze", "circulation", "stuffy"))
        should_run = wants_fan or room_temp >= 26.0
        if self.persona.name == "quiet-comfort":
            speed = "low"
        elif self.persona.name == "cooling-boost" and room_temp >= 27.0:
            speed = "high"
        else:
            speed = "medium"

        actions: list[PlannedAction] = []
        concerns: list[str] = []
        if should_run:
            actions.extend(self._build_actions(device_id=device_id, speed=speed, oscillate=room == "living_room"))
        if topic.sensor_snapshot.quiet_hours and speed == "high":
            concerns.append("High fan speed may be too noisy during quiet hours")

        return AgentProposal(
            agent_name=self.name,
            summary="Fan recommendation prepared from comfort and circulation cues.",
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
            domain_instructions=(
                "Revise your fan plan to reduce noise or overlap with cooling devices when conflicts mention it."
            ),
            fallback_summary="Fan proposal revised after coordination feedback.",
            fallback_rationale="Adjusted fan intensity to align with the shared scene.",
            prior_proposal=prior_proposal,
            revision_request=revision_request,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_revise(prior_proposal, revision_request)

    def _rule_based_revise(
        self,
        prior_proposal: AgentProposal,
        revision_request: RevisionRequest,
    ) -> AgentProposal:
        if not prior_proposal.actions:
            return prior_proposal.model_copy(update={"round_index": revision_request.round_index})

        descriptions = " ".join(conflict.description.lower() for conflict in revision_request.conflicts)
        actions = [action.model_copy(deep=True) for action in prior_proposal.actions]
        if "quiet" in descriptions or "rest" in descriptions or "noise" in descriptions:
            for action in actions:
                if action.attribute == "speed":
                    action.value = "low"
                if action.attribute == "oscillate":
                    action.value = False

        return AgentProposal(
            agent_name=self.name,
            summary="Fan proposal revised after coordination feedback.",
            rationale="Adjusted fan intensity to align with the shared scene.",
            round_index=revision_request.round_index,
            actions=actions,
            concerns=["Fan intensity was reduced after coordination feedback."],
        )
