"""Resolve proposals into a single coordinated plan."""

from __future__ import annotations

from dataclasses import dataclass

from app.agents.catalog import AgentCatalog, default_agent_catalog
from app.core.utils import dedupe_preserve_order
from app.discussion.protocol import AgentProposal, ConflictRecord
from app.planning.action import PlannedAction


@dataclass(frozen=True)
class ActionSelectionPolicy:
    """Policy controlling how many actions may survive final selection."""

    max_agents: int
    max_total_actions: int
    max_actions_per_agent: int
    max_actions_per_device: int


class ActionResolver:
    """Select accepted actions and reject conflicting ones for the MVP."""

    def __init__(self, catalog: AgentCatalog | None = None) -> None:
        self.catalog = catalog or default_agent_catalog(mode="fusion")

    def resolve(
        self,
        proposals: list[AgentProposal],
        conflicts: list[ConflictRecord],
        quiet_hours: bool = False,
        task_source: str = "user_nl",
        task_description: str = "",
        task_preferences: dict | None = None,
        wakeup_scores: dict[str, int] | None = None,
    ) -> tuple[list[PlannedAction], list[PlannedAction], list[str]]:
        accepted: list[PlannedAction] = []
        rejected: list[PlannedAction] = []
        rationale: list[str] = []
        accepted_keys: set[tuple[str, str]] = set()
        task_preferences = task_preferences or {}
        wakeup_scores = wakeup_scores or {}
        policy = self._selection_policy(task_source)
        explicit_agents = self._explicit_agents(task_description, task_preferences)
        proposals_with_actions = [proposal for proposal in proposals if proposal.actions]
        ranked_proposals = self._rank_proposals(
            proposals_with_actions,
            explicit_agents=explicit_agents,
            task_source=task_source,
            wakeup_scores=wakeup_scores,
        )
        selected_proposals, fallback_proposals = self._select_candidate_proposals(
            ranked_proposals,
            task_source=task_source,
            policy=policy,
            explicit_agents=explicit_agents,
            wakeup_scores=wakeup_scores,
        )
        selected_agent_names = {proposal.agent_name for proposal in selected_proposals}

        per_agent_counts: dict[str, int] = {}
        per_device_counts: dict[str, int] = {}

        def evaluate_proposal(proposal: AgentProposal) -> None:
            if proposal.agent_name not in selected_agent_names:
                for action in proposal.actions:
                    rejected.append(
                        action.model_copy(
                            update={
                                "decision_reason": f"Rejected because {proposal.agent_name} was outside the final agent budget."
                            }
                        )
                    )
                return

            candidate_actions = sorted(
                proposal.actions,
                key=lambda action: self._action_priority(
                    action,
                    task_source=task_source,
                    explicit_agents=explicit_agents,
                    wakeup_scores=wakeup_scores,
                ),
                reverse=True,
            )
            for action in candidate_actions:
                key = (action.device_id, action.attribute)
                if not self._is_allowed_by_catalog(proposal.agent_name, action):
                    rejected.append(
                        action.model_copy(
                            update={
                                "decision_reason": f"Rejected because {proposal.agent_name} is not allowed to issue {action.device_id}.{action.attribute}."
                            }
                        )
                    )
                    rationale.append(f"Rejected out-of-scope action {action.device_id}.{action.attribute} from {proposal.agent_name}")
                    continue

                if quiet_hours and action.device_id == "music_player":
                    if action.attribute == "power" and bool(action.value):
                        rejected.append(
                            action.model_copy(
                                update={
                                    "decision_reason": "Rejected because quiet-hours policy blocks music playback."
                                }
                            )
                        )
                        rationale.append("Rejected music power-on request during quiet hours")
                        continue
                    if action.attribute == "volume":
                        try:
                            is_too_loud = int(action.value) > 12
                        except (TypeError, ValueError):
                            is_too_loud = False
                        if is_too_loud:
                            rejected.append(
                                action.model_copy(
                                    update={
                                        "decision_reason": "Rejected because the requested music volume is too high for quiet hours."
                                    }
                                )
                            )
                            rationale.append("Rejected loud music volume during quiet hours")
                            continue

                if len(accepted) >= policy.max_total_actions:
                    rejected.append(
                        action.model_copy(
                            update={
                                "decision_reason": f"Rejected because the task budget allows at most {policy.max_total_actions} final actions."
                            }
                        )
                    )
                    continue

                if per_agent_counts.get(proposal.agent_name, 0) >= policy.max_actions_per_agent:
                    rejected.append(
                        action.model_copy(
                            update={
                                "decision_reason": f"Rejected because {proposal.agent_name} exceeded its final action budget."
                            }
                        )
                    )
                    continue

                if per_device_counts.get(action.device_id, 0) >= policy.max_actions_per_device:
                    rejected.append(
                        action.model_copy(
                            update={
                                "decision_reason": f"Rejected because {action.device_id} already reached the per-device action budget."
                            }
                        )
                    )
                    continue

                if key in accepted_keys:
                    rejected.append(
                        action.model_copy(
                            update={
                                "decision_reason": f"Rejected because {action.device_id}.{action.attribute} already has an accepted value."
                            }
                        )
                    )
                    rationale.append(f"Rejected later duplicate proposal for {action.device_id}.{action.attribute}")
                    continue

                accepted.append(
                    action.model_copy(
                        update={
                            "decision_reason": f"Selected for the coordinated plan by {action.requested_by}."
                        }
                    )
                )
                accepted_keys.add(key)
                per_agent_counts[proposal.agent_name] = per_agent_counts.get(proposal.agent_name, 0) + 1
                per_device_counts[action.device_id] = per_device_counts.get(action.device_id, 0) + 1

        for proposal in ranked_proposals:
            evaluate_proposal(proposal)

        if not accepted and str(task_source or "").lower() == "inferred":
            for fallback in fallback_proposals:
                if fallback.agent_name in selected_agent_names:
                    continue
                selected_agent_names = {fallback.agent_name}
                evaluate_proposal(fallback)
                if accepted:
                    rationale.append(
                        f"Used fallback agent {fallback.agent_name} after the primary inferred-domain proposal yielded no valid final action."
                    )
                    break

        rationale.extend(self._summarize_accepted_actions(accepted))
        if rejected:
            rationale.append("Deferred non-essential or conflicting device changes to keep the plan coherent.")
        if proposals_with_actions and len(selected_agent_names) < len(proposals_with_actions):
            rationale.append("Restricted the final plan to the highest-priority agents to avoid over-activation.")
        if conflicts:
            rationale.extend(conflict.description for conflict in conflicts)

        if not accepted:
            rationale.append("No actionable changes were selected from the discussion round")

        return accepted, rejected, dedupe_preserve_order(rationale, limit=6)

    def _selection_policy(self, task_source: str) -> ActionSelectionPolicy:
        normalized = str(task_source or "user_nl").lower()
        if normalized == "inferred":
            return ActionSelectionPolicy(max_agents=1, max_total_actions=1, max_actions_per_agent=1, max_actions_per_device=1)
        if normalized == "user_nl":
            return ActionSelectionPolicy(max_agents=2, max_total_actions=3, max_actions_per_agent=2, max_actions_per_device=2)
        if normalized == "automation":
            return ActionSelectionPolicy(max_agents=2, max_total_actions=3, max_actions_per_agent=2, max_actions_per_device=2)
        return ActionSelectionPolicy(max_agents=3, max_total_actions=6, max_actions_per_agent=3, max_actions_per_device=3)

    def _explicit_agents(self, task_description: str, task_preferences: dict) -> set[str]:
        haystacks = [str(task_description or "").lower()]
        parsed_slots = task_preferences.get("parsed_slots", {}) if isinstance(task_preferences, dict) else {}
        if isinstance(parsed_slots, dict):
            haystacks.extend(f"{key} {value}".lower() for key, value in parsed_slots.items())
        haystack = " ".join(haystacks)

        matched: set[str] = set()
        for agent_name, profile in self.catalog.profiles.items():
            if any(keyword.lower() in haystack for keyword in profile.keyword_hints):
                matched.add(agent_name)
                continue
            if any(slot.lower() in haystack for slot in profile.slot_hints):
                matched.add(agent_name)
        return matched

    def _rank_proposals(
        self,
        proposals: list[AgentProposal],
        *,
        explicit_agents: set[str],
        task_source: str,
        wakeup_scores: dict[str, int],
    ) -> list[AgentProposal]:
        def score(item: tuple[int, AgentProposal]) -> tuple[int, int]:
            index, proposal = item
            proposal_score = 100 - (index * 5)
            proposal_score += min(len(proposal.actions), 3) * 2
            if proposal.agent_name in explicit_agents:
                proposal_score += 40
            proposal_score += min(wakeup_scores.get(proposal.agent_name, 0), 12) * 6
            if task_source == "inferred" and proposal.agent_name not in explicit_agents:
                proposal_score -= 10
            proposal_score -= len(proposal.concerns)
            proposal_score -= len(proposal.validation_feedback)
            return proposal_score, -index

        ranked = sorted(enumerate(proposals), key=score, reverse=True)
        return [proposal for _, proposal in ranked]

    def _select_candidate_proposals(
        self,
        ranked_proposals: list[AgentProposal],
        *,
        task_source: str,
        policy: ActionSelectionPolicy,
        explicit_agents: set[str],
        wakeup_scores: dict[str, int],
    ) -> tuple[list[AgentProposal], list[AgentProposal]]:
        normalized = str(task_source or "").lower()
        if normalized != "inferred":
            selected = ranked_proposals[: policy.max_agents]
            selected_names = {item.agent_name for item in selected}
            rejected = [proposal for proposal in ranked_proposals if proposal.agent_name not in selected_names]
            return selected, rejected

        primary = self._choose_primary_inferred_proposal(
            ranked_proposals,
            explicit_agents=explicit_agents,
            wakeup_scores=wakeup_scores,
        )
        if primary is None:
            return [], []
        selected = [primary]
        fallbacks = [proposal for proposal in ranked_proposals if proposal.agent_name != primary.agent_name]
        return selected, fallbacks

    def _choose_primary_inferred_proposal(
        self,
        ranked_proposals: list[AgentProposal],
        *,
        explicit_agents: set[str],
        wakeup_scores: dict[str, int],
    ) -> AgentProposal | None:
        if not ranked_proposals:
            return None
        explicit_ranked = [proposal for proposal in ranked_proposals if proposal.agent_name in explicit_agents]
        if explicit_ranked:
            return explicit_ranked[0]
        return max(
            ranked_proposals,
            key=lambda proposal: (
                wakeup_scores.get(proposal.agent_name, 0),
                len(proposal.actions),
                -len(proposal.validation_feedback),
            ),
        )

    def _is_allowed_by_catalog(self, agent_name: str, action: PlannedAction) -> bool:
        profile = self.catalog.profile_for(agent_name)
        if profile is None:
            return True
        allowed = profile.action_targets()
        return action.device_id in allowed and action.attribute in allowed[action.device_id]

    def _action_priority(
        self,
        action: PlannedAction,
        *,
        task_source: str,
        explicit_agents: set[str],
        wakeup_scores: dict[str, int],
    ) -> int:
        priority = {"high": 30, "medium": 20, "low": 10}.get(action.priority, 20)
        if action.requested_by in explicit_agents:
            priority += 20
        priority += min(wakeup_scores.get(action.requested_by, 0), 12) * 3
        if task_source == "inferred":
            if self._is_custom_like_attribute(action.attribute):
                priority += 24
            else:
                priority -= 8
        return priority

    def _is_custom_like_attribute(self, attribute: str) -> bool:
        normalized = str(attribute).lower()
        explicit_service_attrs = {"power", "locked", "target_temperature", "brightness", "position"}
        return normalized not in explicit_service_attrs

    def _summarize_accepted_actions(self, accepted: list[PlannedAction]) -> list[str]:
        summaries: list[str] = []
        has_cooling = any(action.device_id.startswith("living_room_ac") for action in accepted)
        has_lighting = any(action.device_id.startswith("living_room_main") for action in accepted)
        has_music = any(action.device_id == "music_player" for action in accepted)

        if has_cooling:
            summaries.append("Applied moderated cooling to keep the living room comfortable.")
        if has_lighting:
            brightness_action = next(
                (action for action in accepted if action.device_id == "living_room_main" and action.attribute == "brightness"),
                None,
            )
            if brightness_action is not None and int(brightness_action.value) <= 40:
                summaries.append("Adopted low-brightness lighting to support a softer shared scene.")
            else:
                summaries.append("Adjusted lighting to match the requested scene and visibility needs.")
        if has_music:
            volume_action = next(
                (action for action in accepted if action.device_id == "music_player" and action.attribute == "volume"),
                None,
            )
            if volume_action is not None and int(volume_action.value) <= 20:
                summaries.append("Kept music playback gentle so it reinforces the calm scene without dominating it.")
            else:
                summaries.append("Included music playback to strengthen the requested room mood.")
        if accepted:
            summaries.append("Avoided unnecessary device changes outside the selected scene actions.")
        return summaries
