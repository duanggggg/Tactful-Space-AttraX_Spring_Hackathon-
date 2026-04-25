"""Lighting agent for scene and brightness recommendations."""

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


class LightingAgent(BaseAgent):
    """Reason about ambiance, brightness, and disturbance."""

    def __init__(
        self,
        persona_name: str = "balanced",
        workspace_profile: AgentWorkspaceProfile | None = None,
        action_profile: AgentActionProfile | None = None,
        llm_client: ChatModelClient | None = None,
    ) -> None:
        descriptions = {
            "ambiance-first": "Prefers scene-setting and atmospheric lighting.",
            "minimal-disturbance": "Keeps lights subtle to avoid disruption.",
            "balanced": "Balances visibility with mood and comfort.",
        }
        super().__init__(
            name="lighting_agent",
            persona=AgentPersona(
                name=persona_name,
                description=descriptions.get(persona_name, descriptions["balanced"]),
            ),
            workspace_profile=workspace_profile
            or AgentWorkspaceProfile(
                agent_name="lighting_agent",
                workspace_dir=Path("."),
                soul="Shapes room atmosphere with intentional, low-distraction lighting choices.",
                skills=[
                    "Ambient scene lighting",
                    "Brightness calibration by time of day",
                ],
            ),
            capabilities=[
                Capability(
                    name="light_switching",
                    description="Controls power for multiple lights.",
                ),
                Capability(
                    name="brightness_control",
                    description="Adjusts brightness based on task and time of day.",
                ),
            ],
            action_profile=action_profile,
            llm_client=llm_client,
        )

    def allowed_action_targets(self) -> dict[str, set[str]]:
        return {
            "living_room_main": {"power", "brightness", "color", "mode"},
            "bedroom_lamp": {"power", "brightness", "color", "mode"},
        }

    def normalize_action_value(self, attribute: str, value: Any) -> Any:
        value = super().normalize_action_value(attribute, value)
        if attribute == "brightness":
            return max(0, min(100, int(value)))
        return value

    def _build_actions(self, brightness: int) -> list[PlannedAction]:
        return [
            PlannedAction(
                device_id="living_room_main",
                attribute="power",
                value=True,
                reason="Ambient light is low enough to justify illumination",
                requested_by=self.name,
            ),
            PlannedAction(
                device_id="living_room_main",
                attribute="brightness",
                value=brightness,
                reason=f"{self.persona.name} lighting choice",
                requested_by=self.name,
            ),
        ]

    def propose(self, topic: DiscussionTopic) -> AgentProposal:
        fallback_rationale = f"{self.persona.description} {self.memory_summary()}"
        llm_proposal = self.request_llm_proposal(
            topic=topic,
            round_index=1,
            domain_instructions=(
                "Focus on room ambiance, visibility, and disturbance. "
                "You control only the living-room main light."
            ),
            fallback_summary="Lighting recommendation prepared from time-of-day and ambience cues.",
            fallback_rationale=fallback_rationale,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_propose(topic)

    def _rule_based_propose(self, topic: DiscussionTopic) -> AgentProposal:
        description = topic.description.lower()
        parsed_slots = topic.preferences.get("parsed_slots", {}) if isinstance(topic.preferences, dict) else {}
        time_of_day = topic.sensor_snapshot.time_of_day
        brightness = (
            35
            if self.persona.name == "minimal-disturbance"
            else 45
            if time_of_day == "evening"
            else 65
        )
        room = "bedroom" if "bedroom" in description else "living_room"
        device_id = "bedroom_lamp" if room == "bedroom" else "living_room_main"
        brightness_match = re.search(r"(\d{1,3})\s*%", description)
        if brightness_match:
            brightness = max(0, min(100, int(brightness_match.group(1))))
        elif isinstance(parsed_slots, dict) and str(parsed_slots.get("attribute", "")).lower() == "brightness":
            try:
                brightness = max(0, min(100, int(parsed_slots.get("value"))))
            except (TypeError, ValueError):
                pass

        explicit_off = any(keyword in description for keyword in ("turn off", "lights off", "light off"))
        light_on = topic.sensor_snapshot.ambient_light_level < 50 or any(
            keyword in description for keyword in ("light", "lamp", "bright", "dim", "scene", "reading")
        )
        scene_like = any(keyword in description for keyword in ("scene", "movie", "routine", "evening"))

        actions: list[PlannedAction] = []
        if explicit_off:
            actions.append(
                PlannedAction(
                    device_id=device_id,
                    attribute="power",
                    value=False,
                    reason="Task explicitly requested lights off",
                    requested_by=self.name,
                    priority="high",
                )
            )
        elif light_on:
            actions.extend(
                [
                    PlannedAction(
                        device_id=device_id,
                        attribute="power",
                        value=True,
                        reason="Ambient light is low enough to justify illumination",
                        requested_by=self.name,
                    ),
                    PlannedAction(
                        device_id=device_id,
                        attribute="brightness",
                        value=brightness,
                        reason=f"{self.persona.name} lighting choice",
                        requested_by=self.name,
                    ),
                ]
            )
            if scene_like:
                actions.append(
                    PlannedAction(
                        device_id=device_id,
                        attribute="mode",
                        value="static",
                        reason="Scene-like requests benefit from an explicit lighting mode",
                        requested_by=self.name,
                        priority="low",
                    )
                )

        return AgentProposal(
            agent_name=self.name,
            summary="Lighting recommendation prepared from time-of-day and ambience cues.",
            rationale=f"{self.persona.description} {self.memory_summary()}",
            round_index=1,
            actions=actions,
            concerns=["Very dim settings may conflict with task visibility"] if brightness < 40 else [],
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
                "Revise your lighting plan to address coordination conflicts without losing scene coherence."
            ),
            fallback_summary="Lighting proposal revised after coordination feedback.",
            fallback_rationale="Adjusted brightness to better fit the shared scene constraints.",
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
        if not prior_proposal.actions:
            return prior_proposal.model_copy(update={"round_index": revision_request.round_index})

        descriptions = " ".join(
            conflict.description.lower() for conflict in revision_request.conflicts
        )
        brightness = next(
            (action.value for action in prior_proposal.actions if action.attribute == "brightness"),
            45,
        )
        brightness = int(brightness)

        if "sensory" in descriptions or "rest" in descriptions:
            brightness = min(brightness, 35)
        elif "visibility" in descriptions:
            brightness = max(brightness, 50)

        return AgentProposal(
            agent_name=self.name,
            summary="Lighting proposal revised after coordination feedback.",
            rationale="Adjusted brightness to better fit the shared scene constraints.",
            round_index=revision_request.round_index,
            actions=self._build_actions(brightness),
            concerns=["Brightness was revised in response to discussion conflicts."],
        )
