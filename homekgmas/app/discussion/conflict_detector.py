"""Simple conflict detection for MVP coordination."""

from __future__ import annotations

from app.discussion.protocol import AgentProposal, ConflictRecord


class ConflictDetector:
    """Detect direct proposal conflicts and high-level policy mismatches."""

    def detect(
        self,
        proposals: list[AgentProposal],
        quiet_hours: bool = False,
        task_description: str = "",
        time_of_day: str = "evening",
    ) -> list[ConflictRecord]:
        conflicts: list[ConflictRecord] = []
        seen: dict[tuple[str, str], tuple[str, object]] = {}
        brightness: tuple[str, int] | None = None
        volume: tuple[str, int] | None = None
        target_temp: tuple[str, int] | None = None
        task_text = task_description.lower()
        wants_calm_scene = any(keyword in task_text for keyword in ("calm", "soft", "relax", "rest"))

        for proposal in proposals:
            for concern in proposal.concerns:
                concern_text = concern.lower()
                if "quiet-hours" in concern_text:
                    conflicts.append(
                        ConflictRecord(
                            title="Quiet hours conflict",
                            description="Music playback conflicts with quiet-hours policy",
                            agents=[proposal.agent_name],
                            severity="high",
                            resolution_hint="MusicAgent should withdraw playback during quiet hours.",
                        )
                    )
                elif "conflict" in concern_text:
                    conflicts.append(
                        ConflictRecord(
                            title="Proposal concern",
                            description=concern,
                            agents=[proposal.agent_name],
                            severity="medium",
                            resolution_hint="Revise the proposal to better align with the scene constraints.",
                        )
                    )

            for action in proposal.actions:
                key = (action.device_id, action.attribute)
                if key in seen and seen[key][1] != action.value:
                    conflicts.append(
                        ConflictRecord(
                            title="Conflicting device action",
                            description=(
                                f"{action.device_id}.{action.attribute} received "
                                f"multiple values during discussion"
                            ),
                            agents=[seen[key][0], proposal.agent_name],
                            resolution_hint="Agents should converge on one device state before execution.",
                        )
                    )
                else:
                    seen[key] = (proposal.agent_name, action.value)

                if action.device_id == "living_room_main" and action.attribute == "brightness":
                    brightness = (proposal.agent_name, int(action.value))
                if action.device_id == "music_player" and action.attribute == "volume":
                    volume = (proposal.agent_name, int(action.value))
                if action.device_id == "living_room_ac_1" and action.attribute == "target_temperature":
                    target_temp = (proposal.agent_name, int(action.value))

                if quiet_hours and action.device_id == "music_player" and action.attribute == "power":
                    if bool(action.value):
                        conflicts.append(
                            ConflictRecord(
                                title="Quiet hours conflict",
                                description="Music playback conflicts with quiet-hours policy",
                                agents=[proposal.agent_name],
                                severity="high",
                                resolution_hint="MusicAgent should withdraw playback during quiet hours.",
                            )
                        )

        if quiet_hours and volume and volume[1] > 12:
            conflicts.append(
                ConflictRecord(
                    title="Quiet hours volume conflict",
                    description="Music volume exceeds quiet-hours comfort threshold",
                    agents=[volume[0]],
                    severity="high",
                    resolution_hint="Reduce playback volume or disable music entirely.",
                )
            )

        if wants_calm_scene and brightness and volume:
            if brightness[1] > 50 or volume[1] > 20:
                conflicts.append(
                    ConflictRecord(
                        title="Sensory load conflict",
                        description="Combined lighting and music intensity is too strong for a calm scene",
                        agents=[brightness[0], volume[0]],
                        severity="medium",
                        resolution_hint="Reduce brightness and playback volume for a calmer shared scene.",
                    )
                )

        if time_of_day in ("evening", "night") and brightness and brightness[1] > 60:
            conflicts.append(
                ConflictRecord(
                    title="Rest scene brightness conflict",
                    description="Lighting brightness is high for an evening or night scene",
                    agents=[brightness[0]],
                    severity="medium",
                    resolution_hint="Lower the brightness for late-day comfort.",
                )
            )

        if target_temp and target_temp[1] <= 23 and ("energy" in task_text or wants_calm_scene):
            conflicts.append(
                ConflictRecord(
                    title="Energy strain conflict",
                    description="Cooling target is aggressive relative to the requested scene constraints",
                    agents=[target_temp[0]],
                    severity="medium",
                    resolution_hint="Raise the target temperature slightly to reduce energy strain.",
                )
            )

        return conflicts
