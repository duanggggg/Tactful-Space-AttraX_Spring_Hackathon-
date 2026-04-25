"""Structured dialogue compression for long-running discussions."""

from __future__ import annotations

from app.core.utils import dedupe_preserve_order
from app.discussion.protocol import (
    CompressedDiscussionState,
    ConflictRecord,
    DiscussionTurn,
)


class DialogueCompressor:
    """Compress dialogue history into structured coordination state."""

    def __init__(self, window_size: int = 4) -> None:
        self.window_size = window_size

    def compress(
        self,
        turns: list[DiscussionTurn],
        conflicts: list[ConflictRecord] | None = None,
        existing_state: CompressedDiscussionState | None = None,
    ) -> CompressedDiscussionState:
        existing_state = existing_state or CompressedDiscussionState()
        conflicts = conflicts or []

        recent_turns = turns[-self.window_size :]
        rolling_summary = dedupe_preserve_order(
            [
                *existing_state.rolling_summary,
                *[f"{turn.speaker}: {turn.summary}" for turn in recent_turns],
            ],
            limit=max(2, self.window_size),
        )

        return CompressedDiscussionState(
            rolling_summary=rolling_summary,
            open_conflicts=dedupe_preserve_order(conflict.description for conflict in conflicts),
            accepted_decisions=[
                f"{turn.speaker} proposed {turn.proposal_action_count} action(s)"
                for turn in recent_turns
                if turn.proposal_action_count
            ],
            rejected_options=[],
            pending_questions=dedupe_preserve_order([
                "Should conflicts trigger another negotiation round?"
                if conflicts
                else "No pending questions"
            ]),
        )
