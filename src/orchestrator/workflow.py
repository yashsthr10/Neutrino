"""Thin status façade — soft agent loop uses CompletionPolicy for DONE."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkflowFlags:
    """Legacy counters kept for status/tests; CompletionTracker is authoritative."""

    context_resolved: bool = False
    apply_succeeded: bool = False
    tests_succeeded: bool = False
    tests_attempted: bool = False
    lint_succeeded: bool = False
    verification_waived: bool = False
    verify_cycles: int = 0


@dataclass
class WorkflowController:
    """Status labels: INIT → AGENT → DONE | CANCELLED."""

    fsm_state: str = "INIT"
    flags: WorkflowFlags = field(default_factory=WorkflowFlags)
    max_verify_cycles: int = 2

    def start(self) -> tuple[str, str]:
        old = self.fsm_state
        self.fsm_state = "AGENT"
        self.flags = WorkflowFlags()
        return old, self.fsm_state

    def record_tool(self, name: str, *, success: bool) -> None:
        if name == "context.resolve" and success:
            self.flags.context_resolved = True
        if name == "executor.apply" and success:
            self.flags.apply_succeeded = True
        if name == "tests.run":
            self.flags.tests_attempted = True
            self.flags.tests_succeeded = success
            if success:
                self.flags.verification_waived = False
        if name == "lint.run":
            self.flags.lint_succeeded = success

    def mark_verification_waived(self, waived: bool = True) -> None:
        self.flags.verification_waived = waived

    def mark_done(self) -> tuple[str, str]:
        return self._transition("DONE")

    def cancel(self) -> tuple[str, str]:
        return self._transition("CANCELLED")

    def _transition(self, new: str) -> tuple[str, str]:
        old = self.fsm_state
        self.fsm_state = new
        return old, new
