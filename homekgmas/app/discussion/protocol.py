"""Structured discussion models."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from app.core.utils import dedupe_preserve_order, first_sentence, normalize_text_list
from app.planning.action import PlannedAction


class AgentProposal(BaseModel):
    """An agent's structured proposal for the current task."""

    agent_name: str
    summary: str
    rationale: list[str] = Field(default_factory=list)
    round_index: int = 1
    actions: list[PlannedAction] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    validation_feedback: list[str] = Field(default_factory=list)

    @field_validator("summary", mode="before")
    @classmethod
    def normalize_summary(cls, value):
        summary = first_sentence(value)
        return summary or "Proposal prepared."

    @field_validator("rationale", mode="before")
    @classmethod
    def normalize_rationale(cls, value):
        return normalize_text_list(value, max_items=3, fallback=["Used current context to prepare the proposal."])

    @field_validator("concerns", mode="before")
    @classmethod
    def normalize_concerns(cls, value):
        return normalize_text_list(value, max_items=3)


class DiscussionTurn(BaseModel):
    """A discussion turn that can later be compressed."""

    round_index: int = 1
    speaker: str
    summary: str
    turn_type: str = "proposal"
    proposal_action_count: int = 0


class AgentDialogueEntry(BaseModel):
    """Frontend-friendly direct dialogue output for one agent turn."""

    round_index: int = 1
    agent_name: str
    turn_type: str = "proposal"
    summary: str
    rationale: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    validation_feedback: list[str] = Field(default_factory=list)
    actions: list[PlannedAction] = Field(default_factory=list)


class ConflictRecord(BaseModel):
    """A detected conflict among proposals."""

    title: str
    description: str
    agents: list[str] = Field(default_factory=list)
    severity: str = "medium"
    resolution_hint: str = ""


class RevisionRequest(BaseModel):
    """Structured feedback used for a follow-up discussion round."""

    round_index: int
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    accepted_actions: list[PlannedAction] = Field(default_factory=list)
    rejected_actions: list[PlannedAction] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CompressedDiscussionState(BaseModel):
    """Rolling compressed coordination state."""

    rolling_summary: list[str] = Field(default_factory=list)
    open_conflicts: list[str] = Field(default_factory=list)
    accepted_decisions: list[str] = Field(default_factory=list)
    rejected_options: list[str] = Field(default_factory=list)
    pending_questions: list[str] = Field(default_factory=list)

    @field_validator(
        "rolling_summary",
        "open_conflicts",
        "accepted_decisions",
        "rejected_options",
        "pending_questions",
        mode="after",
    )
    @classmethod
    def dedupe_entries(cls, value: list[str]) -> list[str]:
        return dedupe_preserve_order(value)


class DiscussionRoundResult(BaseModel):
    """Structured result of one discussion round."""

    proposals: list[AgentProposal] = Field(default_factory=list)
    proposal_history: list[AgentProposal] = Field(default_factory=list)
    turns: list[DiscussionTurn] = Field(default_factory=list)
    conflicts: list[ConflictRecord] = Field(default_factory=list)
    conflict_history: list[ConflictRecord] = Field(default_factory=list)
    rounds_completed: int = 1
    compressed_state: CompressedDiscussionState = Field(
        default_factory=CompressedDiscussionState
    )
