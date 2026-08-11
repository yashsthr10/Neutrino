"""Minimal agent-loop-local state. Real session state lives in ExecutionContext."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from src.context.runtime.execution_context import ExecutionContext

AgentStatus = Literal[
    "IDLE",
    "RUNNING",
    "WAITING_TOOL",
    "WAITING_USER",
    "COMPLETED",
    "BLOCKED",
    "FAILED",
    "CANCELLED",
]


@dataclass
class AgentLoopState:
    iteration: int = 0
    status: AgentStatus = "IDLE"
    consecutive_failures: int = 0
    same_tool_streak: tuple[str, int] = ("", 0)
    started_at: float = 0.0
    cancel_requested: bool = False
    tokens_used: int = 0
    pending_approval_id: str | None = None
    pending_tool_name: str | None = None
    pending_tool_arguments: dict | None = None


@dataclass(frozen=True, slots=True)
class AgentResult:
    status: AgentStatus
    final_text: str | None
    context: ExecutionContext
    error: str | None = None
    fsm_state: str = "INIT"
    timing: dict | None = None


@dataclass(frozen=True, slots=True)
class PendingApproval:
    request_id: str
    tool_name: str
    arguments: dict = field(default_factory=dict)
    summary: str = ""
