"""ConversationContext — conversational memory slice for one step."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

MessageRole = Literal["user", "assistant", "system", "tool"]
DecisionCategory = Literal["architecture", "coding_preference", "plan", "constraint"]


@dataclass(frozen=True, slots=True)
class Message:
    role: MessageRole
    content: str
    created_at: str
    id: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Decision:
    category: DecisionCategory
    statement: str
    source_message_id: str
    created_at: str
    confidence: float
    id: str = ""


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    text: str
    covers_through_message_id: str
    created_at: str
    tokens_estimate: int


@dataclass(frozen=True, slots=True)
class ConversationContext:
    recent_messages: tuple[Message, ...]
    summary: ConversationSummary | None
    relevant_history: tuple[Message, ...]
    decisions: tuple[Decision, ...]
    tokens_estimate: int
    truncated: bool
