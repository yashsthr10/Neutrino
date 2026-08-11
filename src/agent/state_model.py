"""Soft behavioral agent state (prompt Layer 5) — not a hard FSM."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Phase = Literal["DISCOVER", "PLAN", "IMPLEMENT", "VERIFY", "REPAIR", "DONE"]


@dataclass
class AgentState:
    """Host-derived soft phase shown in the system prompt."""

    phase: Phase = "DISCOVER"
    objective: str = "Understand the requested outcome before acting."
    completed: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)
    next_objective: str = "Inspect the repository as needed."

    def note_completed(self, item: str, *, limit: int = 12) -> None:
        text = item.strip()
        if not text or text in self.completed:
            return
        self.completed.append(text)
        if len(self.completed) > limit:
            self.completed = self.completed[-limit:]

    def note_unknown(self, item: str, *, limit: int = 8) -> None:
        text = item.strip()
        if not text or text in self.unknown:
            return
        self.unknown.append(text)
        if len(self.unknown) > limit:
            self.unknown = self.unknown[-limit:]


def derive_agent_state(
    state: AgentState,
    *,
    tool_name: str | None = None,
    success: bool | None = None,
    apply_succeeded: bool = False,
    checks_required: bool | None = None,
    tests_succeeded: bool = False,
    lint_succeeded: bool = False,
    verification_failed: bool = False,
    has_open_plan_tasks: bool = False,
) -> AgentState:
    """Update soft phase from runtime evidence (advisory only)."""
    if tool_name:
        if success:
            state.note_completed(f"{tool_name} ok")
        elif success is False:
            state.note_unknown(f"{tool_name} failed")

    if verification_failed and apply_succeeded:
        state.phase = "REPAIR"
        state.objective = "Fix the failing verification before declaring completion."
        state.next_objective = "Read the failure output, then apply a targeted fix."
        return state

    # Current tests.run / lint.run success counts even when ctx flags lag.
    verification_passed = (
        tests_succeeded
        or lint_succeeded
        or (tool_name in {"tests.run", "lint.run"} and success is True)
    )

    # Applied + (checks passed or not required) — must run before IMPLEMENT,
    # which also keys off apply_succeeded and would otherwise make this dead.
    if apply_succeeded and (verification_passed or checks_required is False):
        state.phase = "VERIFY"
        state.objective = "Confirm verification evidence before finishing."
        state.next_objective = "Emit a short final if the outcome is satisfied."
        return state

    if tool_name in {"tests.run", "lint.run", "verify.probe", "review.run"}:
        state.phase = "VERIFY"
        state.objective = "Prove the change satisfies the request."
        state.next_objective = "Run or interpret verification evidence."
        return state

    if tool_name == "executor.apply" or apply_succeeded:
        state.phase = "IMPLEMENT"
        state.objective = "Apply the code change."
        if checks_required:
            state.next_objective = "Verify with tests/lint when ready."
        else:
            state.next_objective = "Confirm the change, then finish if complete."
        return state

    if tool_name == "plan.set_tasks" or has_open_plan_tasks:
        if state.phase in {"DISCOVER", "PLAN"}:
            state.phase = "PLAN"
            state.objective = "Structure the work before large edits."
            state.next_objective = "Continue discovery or begin implementation."
        return state

    if tool_name and tool_name.startswith(("rna.", "context.", "research.")):
        if state.phase == "DISCOVER":
            state.objective = "Gather repository evidence for the request."
            state.next_objective = "Narrow to relevant files/symbols, then act."
        return state

    return state
