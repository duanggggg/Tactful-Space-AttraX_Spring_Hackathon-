"""Switch agent for small auxiliary devices."""

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


class SwitchAgent(BaseAgent):
    """Reason about purifier and humidifier usage."""

    def __init__(
        self,
        persona_name: str = "balanced",
        workspace_profile: AgentWorkspaceProfile | None = None,
        action_profile: AgentActionProfile | None = None,
        llm_client: ChatModelClient | None = None,
    ) -> None:
        descriptions = {
            "air-quality-first": "Prioritizes purifier and humidity comfort quickly.",
            "balanced": "Balances air quality support with energy use.",
            "minimalist": "Only activates auxiliary switches when context strongly suggests it.",
        }
        super().__init__(
            name="switch_agent",
            persona=AgentPersona(
                name=persona_name,
                description=descriptions.get(persona_name, descriptions["balanced"]),
            ),
            workspace_profile=workspace_profile
            or AgentWorkspaceProfile(
                agent_name="switch_agent",
                workspace_dir=Path("."),
                soul="Uses helper devices only when they noticeably improve comfort or air quality.",
                skills=[
                    "Purifier control",
                    "Humidifier control",
                ],
            ),
            capabilities=[
                Capability(name="switch_power_control", description="Turns small switch devices on or off."),
                Capability(name="air_support_reasoning", description="Chooses helper devices based on comfort and air cues."),
            ],
            action_profile=action_profile,
            llm_client=llm_client,
        )

    def allowed_action_targets(self) -> dict[str, set[str]]:
        return {
            "air_purifier": {"power", "mode", "humidity"},
            "bedroom_humidifier": {"power", "mode", "humidity"},
        }

    def normalize_action_value(self, attribute: str, value: Any):
        value = super().normalize_action_value(attribute, value)
        if attribute == "mode":
            normalized = str(value).strip().lower()
            return normalized if normalized in {"auto", "sleep", "boost"} else "auto"
        if attribute == "humidity":
            return max(0, min(100, int(value)))
        return value

    def propose(self, topic: DiscussionTopic) -> AgentProposal:
        fallback_rationale = f"{self.persona.description} {self.memory_summary()}"
        llm_proposal = self.request_llm_proposal(
            topic=topic,
            round_index=1,
            domain_instructions=(
                "Focus on purifier and humidifier usefulness. "
                "You control only the air purifier and bedroom humidifier."
            ),
            fallback_summary="Switch-device recommendation prepared from air-quality and comfort cues.",
            fallback_rationale=fallback_rationale,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_propose(topic)

    def _rule_based_propose(self, topic: DiscussionTopic) -> AgentProposal:
        description = topic.description.lower()
        parsed_slots = topic.preferences.get("parsed_slots", {}) if isinstance(topic.preferences, dict) else {}
        humidity = topic.sensor_snapshot.room_humidity_pct
        actions: list[PlannedAction] = []
        if isinstance(parsed_slots, dict) and str(parsed_slots.get("attribute", "")).lower() == "humidity":
            try:
                target_humidity = max(0, min(100, int(parsed_slots.get("value"))))
            except (TypeError, ValueError):
                target_humidity = humidity
            room_text = str(parsed_slots.get("room") or "")
            device_id = "bedroom_humidifier" if any(token in room_text for token in ("卧室", "主卧", "bedroom")) else "air_purifier"
            actions.append(
                PlannedAction(
                    device_id=device_id,
                    attribute="humidity",
                    value=target_humidity,
                    reason="Structured task explicitly requested humidity control",
                    requested_by=self.name,
                    priority="high",
                )
            )
            return AgentProposal(
                agent_name=self.name,
                summary="Switch-device recommendation prepared from air-quality and comfort cues.",
                rationale=f"{self.persona.description} {self.memory_summary()}",
                round_index=1,
                actions=actions,
                concerns=[],
            )

        wants_purifier = any(keyword in description for keyword in ("air", "stuffy", "purifier", "fresh"))
        wants_humidifier = any(keyword in description for keyword in ("humidifier", "dry", "sleep"))
        if wants_purifier or self.persona.name == "air-quality-first":
            actions.extend(
                [
                    PlannedAction(
                        device_id="air_purifier",
                        attribute="power",
                        value=True,
                        reason="Air support device should help current comfort conditions",
                        requested_by=self.name,
                    ),
                    PlannedAction(
                        device_id="air_purifier",
                        attribute="mode",
                        value="boost" if wants_purifier and "stuffy" in description else "auto",
                        reason=f"{self.persona.name} purifier mode selection",
                        requested_by=self.name,
                    ),
                ]
            )
        if wants_humidifier or humidity < 45:
            actions.extend(
                [
                    PlannedAction(
                        device_id="bedroom_humidifier",
                        attribute="power",
                        value=True,
                        reason="Bedroom humidity support could improve comfort",
                        requested_by=self.name,
                    ),
                    PlannedAction(
                        device_id="bedroom_humidifier",
                        attribute="mode",
                        value="sleep" if topic.sensor_snapshot.quiet_hours else "auto",
                        reason="Humidifier mode chosen to fit quietness expectations",
                        requested_by=self.name,
                        priority="low",
                    ),
                ]
            )

        return AgentProposal(
            agent_name=self.name,
            summary="Switch-device recommendation prepared from air-quality and comfort cues.",
            rationale=f"{self.persona.description} {self.memory_summary()}",
            round_index=1,
            actions=actions,
            concerns=[],
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
            domain_instructions="Revise auxiliary-device usage when conflicts mention energy or quietness.",
            fallback_summary="Switch-device proposal revised after coordination feedback.",
            fallback_rationale="Reduced auxiliary-device intensity to better fit shared constraints.",
            prior_proposal=prior_proposal,
            revision_request=revision_request,
        )
        if llm_proposal is not None:
            return llm_proposal
        if not prior_proposal.actions:
            return prior_proposal.model_copy(update={"round_index": revision_request.round_index})

        descriptions = " ".join(conflict.description.lower() for conflict in revision_request.conflicts)
        actions = [action.model_copy(deep=True) for action in prior_proposal.actions]
        if "energy" in descriptions:
            actions = [action for action in actions if action.device_id != "bedroom_humidifier"]
        if "quiet" in descriptions:
            for action in actions:
                if action.attribute == "mode":
                    action.value = "sleep"

        return AgentProposal(
            agent_name=self.name,
            summary="Switch-device proposal revised after coordination feedback.",
            rationale="Reduced auxiliary-device intensity to better fit shared constraints.",
            round_index=revision_request.round_index,
            actions=actions,
            concerns=["Auxiliary-device usage was reduced after coordination feedback."],
        )
