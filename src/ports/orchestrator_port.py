"""Orchestrator port and UI-facing event types. TUI depends only on this module."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol, Union

# --- Events (immutable snapshots for the TUI) ---


@dataclass(frozen=True, slots=True)
class PhaseMarker:
    """Live execution phase label, e.g. PLAN, EXECUTE, VERIFY."""

    phase: str


@dataclass(frozen=True, slots=True)
class StateTransition:
    from_state: str
    to_state: str


@dataclass(frozen=True, slots=True)
class TokenUpdate:
    used: int
    budget: int | None = None


@dataclass(frozen=True, slots=True)
class ToolCallEvent:
    name: str
    args_summary: str
    success: bool


@dataclass(frozen=True, slots=True)
class LogLine:
    """Structured log for the Logs panel."""

    message: str
    level: Literal["info", "warning", "error"] = "info"


@dataclass(frozen=True, slots=True)
class AgentMessage:
    content: str
    final: bool = False


@dataclass(frozen=True, slots=True)
class ReasoningBlock:
    content: str
    collapsed_default: bool = True


@dataclass(frozen=True, slots=True)
class DiffChunk:
    path: str
    old_text: str
    new_text: str


@dataclass(frozen=True, slots=True)
class ApprovalRequest:
    request_id: str
    summary: str
    preview_snippet: str = ""
    full_file_text: str | None = None


@dataclass(frozen=True, slots=True)
class RepoTreeSnapshot:
    """Flat or nested paths for the file explorer."""

    root_label: str
    paths: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class StatusSnapshot:
    """Maps to ExecutionContext-aligned status bar."""

    mode_label: str
    tokens_used: int
    fsm_state: str
    task_complexity: str = "MEDIUM"


@dataclass(frozen=True, slots=True)
class RunFinished:
    ok: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class ThinkingDelta:
    """Append text to the current phase block (streaming)."""

    phase_id: str
    text: str
    append_newline: bool = True


@dataclass(frozen=True, slots=True)
class PhaseStepComplete:
    """Mark a sub-step within a phase as done."""

    phase_id: str
    message: str


@dataclass(frozen=True, slots=True)
class ContextFileInfo:
    path: str
    line_count: int


@dataclass(frozen=True, slots=True)
class ContextEdge:
    from_path: str
    to_path: str


@dataclass(frozen=True, slots=True)
class ContextSummary:
    """Structured context for inspector (not parsed from log)."""

    files: tuple[ContextFileInfo, ...]
    edges: tuple[ContextEdge, ...]
    tokens_used: int
    token_budget: int | None = None


@dataclass(frozen=True, slots=True)
class FailureRecovery:
    message: str
    options: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ExplanationAvailable:
    bullets: tuple[str, ...]


UIEvent = Union[
    PhaseMarker,
    StateTransition,
    TokenUpdate,
    ToolCallEvent,
    LogLine,
    AgentMessage,
    ReasoningBlock,
    DiffChunk,
    ApprovalRequest,
    RepoTreeSnapshot,
    StatusSnapshot,
    RunFinished,
    ThinkingDelta,
    PhaseStepComplete,
    ContextSummary,
    FailureRecovery,
    ExplanationAvailable,
]


@dataclass
class ApprovalResponse:
    request_id: str
    approved: bool


RuntimeMode = Literal["fast", "deep", "auto"]
ApprovalAction = Literal["accept", "edit", "reject", "view"]


class OrchestratorPort(Protocol):
    """Backend brain: FSM, agents, tools. TUI talks only through this port."""

    def submit_task(self, user_query: str) -> None:
        """Start a run for the given user task."""
        ...

    def send_approval(self, request_id: str, approved: bool) -> None: ...

    def send_approval_action(self, request_id: str, action: ApprovalAction) -> None: ...

    def submit_approval_edit(self, request_id: str, new_text: str) -> None: ...

    def set_runtime_mode(self, mode: RuntimeMode) -> None:
        """Maps to orchestrator presets (token budget, branching, etc.)."""
        ...

    def request_retry(self) -> None: ...

    def request_context_refresh(self) -> None: ...

    def request_repo_tree(self) -> None:
        """Populate or refresh file explorer data."""
        ...

    def select_recovery_option(self, option_id: str) -> None: ...

    def cancel_run(self) -> None:
        """Cancel the current task (distinct from quitting the app)."""
        ...
