"""Music agent for local media recommendations."""

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
from app.environment.constraints import music_allowed
from app.llm.client import ChatModelClient
from app.orchestrator.topic_builder import DiscussionTopic
from app.planning.action import PlannedAction


class MusicAgent(BaseAgent):
    """Reason about playlists, volume, and quiet-hours constraints."""

    def __init__(
        self,
        persona_name: str = "balanced",
        workspace_profile: AgentWorkspaceProfile | None = None,
        action_profile: AgentActionProfile | None = None,
        llm_client: ChatModelClient | None = None,
    ) -> None:
        descriptions = {
            "mood-enhancing": "Uses music to shape the room's emotional tone.",
            "conservative": "Avoids unnecessary playback unless clearly helpful.",
            "balanced": "Uses music when it supports the current task context.",
        }
        super().__init__(
            name="music_agent",
            persona=AgentPersona(
                name=persona_name,
                description=descriptions.get(persona_name, descriptions["balanced"]),
            ),
            workspace_profile=workspace_profile
            or AgentWorkspaceProfile(
                agent_name="music_agent",
                workspace_dir=Path("."),
                soul="Uses gentle audio scenes to support mood without violating house policies.",
                skills=[
                    "Music playback selection",
                    "Volume moderation for shared spaces",
                ],
            ),
            capabilities=[
                Capability(
                    name="playback_control",
                    description="Turns playback on or off and changes playlist.",
                ),
                Capability(
                    name="volume_control",
                    description="Adjusts playback volume for scene suitability.",
                ),
            ],
            action_profile=action_profile,
            llm_client=llm_client,
        )

    def allowed_action_targets(self) -> dict[str, set[str]]:
        return {
            "music_player": {"power", "playlist", "volume", "input_source", "brightness", "equalizer", "media_track"},
        }

    def normalize_action_value(self, attribute: str, value: Any) -> Any:
        value = super().normalize_action_value(attribute, value)
        if attribute == "volume":
            return max(0, min(100, int(value)))
        if attribute == "playlist":
            return str(value).strip() or "soft_instrumental"
        if attribute == "brightness":
            return max(0, min(100, int(value)))
        if attribute == "media_track":
            return max(1, int(value))
        if attribute in {"input_source", "equalizer"}:
            return str(value).strip() or "balanced"
        return value

    def _build_actions(self, playlist: str, volume: int) -> list[PlannedAction]:
        return [
            PlannedAction(
                device_id="music_player",
                attribute="power",
                value=True,
                reason="Task tone suggests background music would help",
                requested_by=self.name,
            ),
            PlannedAction(
                device_id="music_player",
                attribute="playlist",
                value=playlist,
                reason=f"{self.persona.name} playlist selection",
                requested_by=self.name,
            ),
            PlannedAction(
                device_id="music_player",
                attribute="volume",
                value=volume,
                reason="Volume matched to a calm shared-space scene",
                requested_by=self.name,
            ),
        ]

    def propose(self, topic: DiscussionTopic) -> AgentProposal:
        fallback_rationale = f"{self.persona.description} {self.memory_summary()}"
        llm_proposal = self.request_llm_proposal(
            topic=topic,
            round_index=1,
            domain_instructions=(
                "Focus on playback usefulness, emotional tone, and quiet-hours constraints. "
                "You control only the shared music player."
            ),
            fallback_summary="Music recommendation prepared from scene and policy cues.",
            fallback_rationale=fallback_rationale,
        )
        if llm_proposal is not None:
            return llm_proposal
        return self._rule_based_propose(topic)

    def _rule_based_propose(self, topic: DiscussionTopic) -> AgentProposal:
        description = topic.description.lower()
        parsed_slots = topic.preferences.get("parsed_slots", {}) if isinstance(topic.preferences, dict) else {}
        wants_music = any(keyword in description for keyword in ("music", "calm", "relax", "party", "speaker", "playlist"))
        wants_media = any(keyword in description for keyword in ("television", "tv", "settop", "movie", "netflix", "volume", "mute", "channel"))
        volume_match = re.search(r"(\d{1,3})\s*%", description)
        explicit_volume = None
        if volume_match:
            explicit_volume = max(0, min(100, int(volume_match.group(1))))
        elif isinstance(parsed_slots, dict) and str(parsed_slots.get("attribute", "")).lower() in {"volume", "volume_level"}:
            try:
                explicit_volume = max(0, min(100, int(parsed_slots.get("value"))))
            except (TypeError, ValueError):
                explicit_volume = None
        actions: list[PlannedAction] = []
        concerns: list[str] = []

        if explicit_volume is not None:
            actions.append(
                PlannedAction(
                    device_id="music_player",
                    attribute="volume",
                    value=explicit_volume,
                    reason="Task explicitly requested a target media volume",
                    requested_by=self.name,
                    priority="high",
                )
            )
        elif wants_media:
            input_source = "netflix" if "netflix" in description else "television" if any(term in description for term in ("television", "tv", "settop")) else "home"
            actions.append(
                PlannedAction(
                    device_id="music_player",
                    attribute="input_source",
                    value=input_source,
                    reason="Recent or explicit media intent suggests switching the active source",
                    requested_by=self.name,
                    priority="high",
                )
            )
            if "mute" in description:
                actions.append(
                    PlannedAction(
                        device_id="music_player",
                        attribute="volume",
                        value=0,
                        reason="Task explicitly requested muting media playback",
                        requested_by=self.name,
                    )
                )
        elif wants_music and music_allowed(topic.sensor_snapshot):
            playlist = "evening_chill" if self.persona.name != "conservative" else "soft_instrumental"
            volume = 28 if self.persona.name == "mood-enhancing" else 18
            actions.extend(self._build_actions(playlist=playlist, volume=volume))
        elif wants_music or wants_media:
            concerns.append("Music request conflicts with quiet-hours policy")

        return AgentProposal(
            agent_name=self.name,
            summary="Music recommendation prepared from scene and policy cues.",
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
                "Revise your playback plan to satisfy policy and shared-scene conflicts. "
                "If quiet hours apply, remove playback."
            ),
            fallback_summary="Music proposal revised after coordination feedback.",
            fallback_rationale="Playback intensity was reduced to better align with the shared scene.",
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
        descriptions = " ".join(
            conflict.description.lower() for conflict in revision_request.conflicts
        )
        if "quiet-hours" in descriptions or topic.sensor_snapshot.quiet_hours:
            return AgentProposal(
                agent_name=self.name,
                summary="Music proposal withdrawn after quiet-hours conflict.",
                rationale="Playback was removed to satisfy the environment policy.",
                round_index=revision_request.round_index,
                actions=[],
                concerns=["Playback suppressed during quiet hours."],
            )

        if not prior_proposal.actions:
            return prior_proposal.model_copy(update={"round_index": revision_request.round_index})

        volume = next(
            (action.value for action in prior_proposal.actions if action.attribute == "volume"),
            18,
        )
        volume = int(volume)
        if "sensory" in descriptions or "rest" in descriptions:
            volume = min(volume, 12)

        playlist = next(
            (action.value for action in prior_proposal.actions if action.attribute == "playlist"),
            "soft_instrumental",
        )
        return AgentProposal(
            agent_name=self.name,
            summary="Music proposal revised after coordination feedback.",
            rationale="Playback intensity was reduced to better align with the shared scene.",
            round_index=revision_request.round_index,
            actions=self._build_actions(playlist=str(playlist), volume=volume),
            concerns=["Playback volume was reduced in response to discussion conflicts."],
        )
