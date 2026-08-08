"""Standard inference response and stream events."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.inference.models.request import ToolCall
from src.inference.models.usage import Usage

FinishReason = Literal["stop", "tool_calls", "length", "content_filter", "error", "unknown"]


@dataclass(frozen=True, slots=True)
class InferenceResponse:
    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    usage: Usage = field(default_factory=Usage)
    finish_reason: FinishReason = "unknown"
    model: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InferenceStreamEvent:
    type: Literal["delta_text", "tool_call_delta", "usage", "done", "error"]
    text: str | None = None
    tool_call: ToolCall | None = None
    usage: Usage | None = None
    finish_reason: FinishReason | None = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class HealthStatus:
    ok: bool
    message: str = ""
    models: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelInfo:
    id: str
    owned_by: str | None = None
