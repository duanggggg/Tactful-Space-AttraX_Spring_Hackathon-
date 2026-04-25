"""Low-level discussion message primitives."""

from __future__ import annotations

from pydantic import BaseModel


class DiscussionMessage(BaseModel):
    """One structured discussion utterance."""

    sender: str
    content: str
    message_type: str = "proposal"
