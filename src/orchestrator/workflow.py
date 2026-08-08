"""Minimal FSM authority — decides phase transitions and DONE."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class WorkflowFlags:
    context_resolved: bool = False
    apply_succeeded: bool = False
    tests_succeeded: bool = False
    tests_attempted: bool = False
    lint_succeeded: bool = False
    verification_waived: bool = False
    verify_cycles: int = 0


@dataclass
class WorkflowController:
    """Runtime-owned phase machine. The model does not choose DONE."""

    fsm_state: str = "INIT"
    flags: WorkflowFlags = field(default_factory=WorkflowFlags)
    max_verify_cycles: int = 2
    """Bounded retries for VERIFY -> EXECUTE when verification fails."""

    def start(self) -> tuple[str, str]:
        """INIT → PLAN. Returns (from, to)."""
        old = self.fsm_state
        self.fsm_state = "PLAN"
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

    def verification_passed(self, *, lint_only: bool = False) -> bool:
        if self.flags.verification_waived:
            return True
        if self.flags.tests_succeeded:
            return True
        if lint_only and self.flags.lint_succeeded:
            return True
        return False

    def after_agent_result(
        self, *, agent_final: bool, lint_only: bool = False
    ) -> tuple[str, str] | None:
        """
        Possibly transition after a phase AgentResult.

        Returns (from, to) if transitioned, else None.
        ``lint_only`` lets a green ``lint.run`` satisfy VERIFY when the repo has
        lint tooling but no test harness.
        """
        if not agent_final and self.fsm_state != "PLAN":
            # Mid-phase tool-only pause (WAITING_USER) — no transition
            return None

        if self.fsm_state == "PLAN":
            if agent_final or self.flags.context_resolved:
                return self._transition("EXECUTE")
            return None

        if self.fsm_state == "EXECUTE":
            if agent_final and self.flags.apply_succeeded:
                return self._transition("VERIFY")
            return None

        if self.fsm_state == "VERIFY":
            if not agent_final:
                return None
            if self.verification_passed(lint_only=lint_only):
                return self._transition("DONE")
            # Verification did not prove the change — send it back to EXECUTE for a
            # bounded number of fix-up attempts before giving up for good.
            if self.flags.verify_cycles < self.max_verify_cycles:
                self.flags.verify_cycles += 1
                self._reset_verify_attempt_flags()
                return self._transition("EXECUTE")
            return None

        return None

    def cancel(self) -> tuple[str, str]:
        return self._transition("CANCELLED")

    def _reset_verify_attempt_flags(self) -> None:
        self.flags.apply_succeeded = False
        self.flags.tests_succeeded = False
        self.flags.tests_attempted = False
        self.flags.lint_succeeded = False
        self.flags.verification_waived = False

    def _transition(self, new: str) -> tuple[str, str]:
        old = self.fsm_state
        self.fsm_state = new
        return old, new
