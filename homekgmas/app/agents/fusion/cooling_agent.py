"""Cooling agent for air-conditioner control proposals."""

from __future__ import annotations

from pathlib import Path
import re
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


class CoolingAgent(BaseAgent):
    """Reason about thermal comfort and energy trade-offs."""

    def __init__(
        self,
        persona_name: str = "balanced",
        workspace_profile: AgentWorkspaceProfile | None = None,
        action_profile: AgentActionProfile | None = None,
        llm_client: ChatModelClient | None = None,
    ) -> None:
        descriptions = {
            "comfort-first": "Prioritizes thermal comfort and faster cooling.",
            "balanced": "Balances comfort with moderate energy usage.",
            "energy-aware": "Favors minimal energy usage while maintaining comfort.",
        }
        super().__init__(
            name="cooling_agent",
            persona=AgentPersona(
                name=persona_name,
                description=descriptions.get(persona_name, descriptions["balanced"]),
            ),
            workspace_profile=workspace_profile
            or AgentWorkspaceProfile(
                agent_name="cooling_agent",
                workspace_dir=Path("."),
                soul="Maintains calm thermal comfort while avoiding abrupt, wasteful cooling decisions.",
                skills=[
                    "Temperature control for the living-room AC",
                    "Occupancy-aware cooling adjustments",
                ],
            ),
            capabilities=[
                Capability(
                    name="temperature_control",
                    description="Adjust AC power, mode, target temperature, and fan speed.",
                ),
                Capability(
                    name="occupancy_reasoning",
                    description="Uses occupancy and thermal context to choose devices.",
                ),
            ],
            action_profile=action_profile,
            llm_client=llm_client,
        )

    def allowed_action_targets(self) -> dict[str, set[str]]:
        return {
            "living_room_ac_1": {"power", "target_temperature", "fan_speed", "mode"},
            "bedroom_ac_1": {"power", "target_temperature", "fan_speed", "mode"},
        }

    def normalize_action_value(self, attribute: str, value: Any) -> Any:
        value = super().normalize_action_value(attribute, value)
        if attribute == "target_temperature":
            return max(18, min(30, int(value)))
        if attribute == "fan_speed":
            normalized = str(value).strip().lower()
            return normalized if normalized in {"low", "medium", "high", "auto"} else "medium"
        if attribute == "mode":
            normalized = str(value).strip().lower()
            return normalized if normalized in {"cool", "sleep", "dry", "fan"} else "cool"
        return value

    def _build_actions(self, device_id: str, desired_temp: int, fan_speed: str) -> list[PlannedAction]:
        return [
            PlannedAction(
                device_id=device_id,
                attribute="power",
                value=True,
                reason="Living room appears warm and occupied",
                requested_by=self.name,
                priority="high",
            ),
            PlannedAction(
                device_id=device_id,
                attribute="target_temperature",
                value=desired_temp,
                reason=f"{self.persona.name} cooling target",
                requested_by=self.name,
            ),
            PlannedAction(
                device_id=device_id,
                attribute="fan_speed",
                value=fan_speed,
                reason="Moderate airflow for current comfort target",
                requested_by=self.name,
            ),
        ]

    def propose(self, topic: DiscussionTopic) -> AgentProposal:
        fallback_rationale = f"{self.persona.description} {self.memory_summary()}"
        llm_proposal = self.request_llm_proposal(
            topic=topic,
            round_index=1,
            domain_instructions=(
                "Focus on thermal comfort, occupancy, and energy trade-offs. "
                "You control only the living-room air conditioner."
            ),
            fallback_summary="Cooling recommendation prepared from temperature and occupancy context.",
            fallback_rationale=fallback_rationale,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_propose(topic)

    def _rule_based_propose(self, topic: DiscussionTopic) -> AgentProposal:
        sensors = topic.sensor_snapshot
        description = topic.description.lower()
        parsed_slots = topic.preferences.get("parsed_slots", {}) if isinstance(topic.preferences, dict) else {}
        desired_temp = (
            23
            if self.persona.name == "comfort-first"
            else 24
            if self.persona.name == "balanced"
            else 25
        )
        temperature_match = re.search(r"(\d{2})\s*(?:c|degrees?)", description)
        if temperature_match:
            desired_temp = max(18, min(30, int(temperature_match.group(1))))
        elif isinstance(parsed_slots, dict) and str(parsed_slots.get("attribute", "")).lower() in {"temperature", "target_temperature"}:
            try:
                desired_temp = max(18, min(30, int(parsed_slots.get("value"))))
            except (TypeError, ValueError):
                pass

        target_room = "bedroom" if "bedroom" in description else "living_room"
        device_id = "bedroom_ac_1" if target_room == "bedroom" else "living_room_ac_1"
        explicit_off = any(keyword in description for keyword in ("turn off", "stop cooling", "ac off"))
        should_cool = sensors.room_temperature_c >= 26 or any(
            keyword in description for keyword in ("cool", "temperature", "ac", "warm", "hot", "climate")
        )
        actions: list[PlannedAction] = []

        if explicit_off:
            actions.append(
                PlannedAction(
                    device_id=device_id,
                    attribute="power",
                    value=False,
                    reason="Task explicitly requested climate shutdown",
                    requested_by=self.name,
                    priority="high",
                )
            )
        elif should_cool:
            actions.extend(self._build_actions(
                device_id=device_id,
                desired_temp=desired_temp,
                fan_speed="medium" if self.persona.name != "comfort-first" else "high",
            ))
            actions.append(
                PlannedAction(
                    device_id=device_id,
                    attribute="mode",
                    value="cool",
                    reason="Explicitly keep the climate system in cooling mode",
                    requested_by=self.name,
                    priority="low",
                )
            )

        return AgentProposal(
            agent_name=self.name,
            summary="Cooling recommendation prepared from temperature and occupancy context.",
            rationale=f"{self.persona.description} {self.memory_summary()}",
            round_index=1,
            actions=actions,
            concerns=["High cooling may conflict with energy-saving goals"] if actions else [],
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
                "Revise your prior cooling plan in response to coordination conflicts. "
                "Keep comfort reasonable while reducing unnecessary energy use when conflicts mention it."
            ),
            fallback_summary="Cooling proposal revised after coordination feedback.",
            fallback_rationale="Adjusted cooling aggressiveness to reduce coordination conflicts.",
            prior_proposal=prior_proposal,
            revision_request=revision_request,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_revise(topic, prior_proposal, revision_request)

    def _rule_based_revise(
        self,
        topic: DiscussionTopic,
        prior_proposal: AgentProposal,
        revision_request: RevisionRequest,
    ) -> AgentProposal:
        involved_agents = {agent for conflict in revision_request.conflicts for agent in conflict.agents}
        if self.name not in involved_agents or not prior_proposal.actions:
            return prior_proposal.model_copy(update={"round_index": revision_request.round_index})

        descriptions = " ".join(
            conflict.description.lower() for conflict in revision_request.conflicts
        )
        desired_temp = 24 if self.persona.name == "comfort-first" else 25
        if "energy" in descriptions:
            desired_temp = max(desired_temp, 25)
        fan_speed = "low" if "sensory" in descriptions or "rest" in descriptions else "medium"

        return AgentProposal(
            agent_name=self.name,
            summary="Cooling proposal revised after coordination feedback.",
            rationale="Adjusted cooling aggressiveness to reduce coordination conflicts.",
            round_index=revision_request.round_index,
            actions=self._build_actions(
                device_id=prior_proposal.actions[0].device_id,
                desired_temp=desired_temp,
                fan_speed=fan_speed,
            ),
            concerns=["Cooling was softened to better align with shared constraints."],
        )
