"""Combine discussion proposals into a coordinated execution plan."""

from __future__ import annotations

from app.core.utils import dedupe_preserve_order
from app.discussion.action_resolver import ActionResolver
from app.discussion.conflict_detector import ConflictDetector
from app.discussion.protocol import DiscussionRoundResult
from app.memory.dialogue_compressor import DialogueCompressor
from app.planning.plan import ExecutionPlan


class ConsensusManager:
    """Runs conflict detection, compression refresh, and action resolution."""

    def __init__(
        self,
        conflict_detector: ConflictDetector,
        action_resolver: ActionResolver,
        compressor: DialogueCompressor,
    ) -> None:
        self.conflict_detector = conflict_detector
        self.action_resolver = action_resolver
        self.compressor = compressor

    def build_plan(
        self,
        task_id: str,
        discussion_result: DiscussionRoundResult,
        quiet_hours: bool,
        task_source: str,
        task_description: str,
        task_preferences: dict | None,
        time_of_day: str,
        wakeup_scores: dict[str, int] | None = None,
    ) -> tuple[ExecutionPlan, DiscussionRoundResult]:
        conflicts = discussion_result.conflicts or self.conflict_detector.detect(
            discussion_result.proposals,
            quiet_hours=quiet_hours,
            task_description=task_description,
            time_of_day=time_of_day,
        )
        historical_conflicts = discussion_result.conflict_history or conflicts
        accepted, rejected, rationale = self.action_resolver.resolve(
            discussion_result.proposals,
            conflicts,
            quiet_hours=quiet_hours,
            task_source=task_source,
            task_description=task_description,
            task_preferences=task_preferences,
            wakeup_scores=wakeup_scores,
        )
        if historical_conflicts:
            rationale.extend(conflict.description for conflict in historical_conflicts)
        discussion_result.conflicts = conflicts
        discussion_result.conflict_history = historical_conflicts
        discussion_result.compressed_state = self.compressor.compress(
            discussion_result.turns,
            conflicts=conflicts,
            existing_state=discussion_result.compressed_state,
        )

        conflict_count = len(historical_conflicts)
        consensus_level = "high" if conflict_count == 0 else "medium" if conflict_count <= 2 else "low"
        decision_confidence = max(0.2, min(0.98, 0.92 - (0.16 * conflict_count) - (0.03 * len(rejected))))
        policy_checks_passed = ["action_schema_valid", "deduplicated_device_targets"]
        if quiet_hours:
            policy_checks_passed.append("quiet_hours_respected")
        if not conflicts:
            policy_checks_passed.append("no_open_conflicts")

        plan = ExecutionPlan(
            task_id=task_id,
            selected_actions=accepted,
            rejected_actions=rejected,
            rationale=dedupe_preserve_order(rationale, limit=6),
            conflicts=[conflict.description for conflict in historical_conflicts],
            decision_confidence=round(decision_confidence, 2),
            consensus_level=consensus_level,
            policy_checks_passed=policy_checks_passed,
        )
        return plan, discussion_result
