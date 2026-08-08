"""Standard inference request models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

Role = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    id: str
    name: str
    arguments: str  # JSON string


@dataclass(frozen=True, slots=True)
class Message:
    role: Role
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: tuple[ToolCall, ...] = ()
    name: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSpec:
    """OpenAI-style tool schema (compatible with Tool Engine export)."""

    name: str
    description: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InferenceRequest:
    messages: tuple[Message, ...]
    model: str | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    tools: tuple[ToolSpec, ...] = ()
    tool_choice: str | dict[str, Any] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
