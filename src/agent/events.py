"""Agent-loop observability events (mapped to UIEvent by the orchestrator)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, Union


@dataclass(frozen=True, slots=True)
class AgentIterationStarted:
    iteration: int
    fsm_state: str


@dataclass(frozen=True, slots=True)
class ModelInvoked:
    iteration: int
    tool_count: int


@dataclass(frozen=True, slots=True)
class ModelCompleted:
    iteration: int
    latency_ms: float
    input_tokens: int = 0
    output_tokens: int = 0
    tool_count: int = 0
    """Number of tools offered to the model (schema catalog size)."""
    response_tool_calls: int = 0
    """Number of tool calls returned in the model response."""
    finish_reason: str | None = None
    outcome: str | None = None
    content_preview: str | None = None
    tool_call_preview: str | None = None


@dataclass(frozen=True, slots=True)
class ModelStreamDelta:
    """Incremental model output while streaming (reasoning or answer text)."""

    channel: Literal["reasoning", "content"]
    text: str
    fsm_state: str


@dataclass(frozen=True, slots=True)
class ToolCallRequested:
    name: str
    arguments: dict[str, Any]
    tool_call_id: str


@dataclass(frozen=True, slots=True)
class ToolCallCompleted:
    name: str
    success: bool
    error: str | None = None
    summary: str = ""
    cost_ms: float = 0.0


@dataclass(frozen=True, slots=True)
class AgentIterationCompleted:
    iteration: int
    outcome: Literal["tool_calls", "final", "invalid", "error", "blocked", "cancelled"]


@dataclass(frozen=True, slots=True)
class AgentBlocked:
    reason: str


@dataclass(frozen=True, slots=True)
class AgentCompleted:
    final_text: str | None


@dataclass(frozen=True, slots=True)
class AgentFailed:
    reason: str


@dataclass(frozen=True, slots=True)
class AgentWaitingUser:
    request_id: str
    tool_name: str
    summary: str


@dataclass(frozen=True, slots=True)
class TimingSummary:
    """End-of-run (or on-demand) timing snapshot lines + dict."""

    lines: tuple[str, ...]
    stats: dict[str, Any]


AgentEvent = Union[
    AgentIterationStarted,
    ModelInvoked,
    ModelCompleted,
    ModelStreamDelta,
    ToolCallRequested,
    ToolCallCompleted,
    AgentIterationCompleted,
    AgentBlocked,
    AgentCompleted,
    AgentFailed,
    AgentWaitingUser,
    TimingSummary,
]
