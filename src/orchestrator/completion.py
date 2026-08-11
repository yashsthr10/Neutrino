"""CompletionPolicy — runtime-owned DONE without hard PLAN→EXECUTE→VERIFY."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from src.context.runtime.execution_context import ExecutionContext
from src.verification.harness import VerificationPolicy, build_verification_policy


class CompletionDecisionKind(str, Enum):
    DONE = "DONE"
    CONTINUE = "CONTINUE"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, slots=True)
class CompletionDecision:
    kind: CompletionDecisionKind
    reason: str
    checks_required: bool | None = None
    policy_reason: str | None = None
    nudge: str | None = None


@dataclass
class CompletionTracker:
    """Tracks verify/repair cycles for a single agent run."""

    max_verify_cycles: int = 2
    verify_cycles: int = 0
    tests_succeeded: bool = False
    lint_succeeded: bool = False
    tests_attempted: bool = False
    apply_succeeded: bool = False
    verification_waived: bool = False

    def record_tool(self, name: str, *, success: bool) -> None:
        if name == "executor.apply" and success:
            self.apply_succeeded = True
        if name == "tests.run":
            self.tests_attempted = True
            self.tests_succeeded = success
            if success:
                self.verification_waived = False
        if name == "lint.run":
            self.lint_succeeded = success


def evaluate_completion(
    ctx: ExecutionContext,
    tracker: CompletionTracker,
    *,
    repo_path: Path,
    agent_final: bool,
) -> CompletionDecision:
    if not agent_final:
        return CompletionDecision(CompletionDecisionKind.CONTINUE, "not_final")

    if not tracker.apply_succeeded and not _has_apply_in_ctx(ctx):
        return CompletionDecision(
            CompletionDecisionKind.DONE,
            "no_writes",
            checks_required=False,
            policy_reason="question_or_explore",
        )

    # Ensure apply flag if context already recorded changes.
    if _has_apply_in_ctx(ctx):
        tracker.apply_succeeded = True

    policy = build_verification_policy(
        repo_path,
        code_changes=ctx.execution.code_changes,
        user_query=ctx.request.user_query,
    )
    lint_only = policy.reason == "lint_harness_present"

    if not policy.checks_required:
        tracker.verification_waived = True
        return CompletionDecision(
            CompletionDecisionKind.DONE,
            "checks_waived",
            checks_required=False,
            policy_reason=policy.reason,
        )

    if _verification_passed(tracker, lint_only=lint_only):
        return CompletionDecision(
            CompletionDecisionKind.DONE,
            "checks_green",
            checks_required=True,
            policy_reason=policy.reason,
        )

    # Failed or missing verification — repair loop.
    if tracker.verify_cycles >= tracker.max_verify_cycles:
        return CompletionDecision(
            CompletionDecisionKind.BLOCKED,
            "tests_not_green",
            checks_required=True,
            policy_reason=policy.reason,
            nudge=(
                "Verification did not pass after the maximum repair attempts. "
                "Summarize the blocker."
            ),
        )

    tracker.verify_cycles += 1
    return CompletionDecision(
        CompletionDecisionKind.CONTINUE,
        "need_verification",
        checks_required=True,
        policy_reason=policy.reason,
        nudge=(
            "Code was modified but verification is still required. "
            "Call verify.probe if needed, then tests.run and/or lint.run. "
            "If checks fail, fix with executor.apply (Update File / search_replace "
            "for existing paths), then re-verify."
        ),
    )


def refresh_policy_on_context(
    ctx: ExecutionContext, repo_path: Path
) -> tuple[ExecutionContext, VerificationPolicy]:
    from src.context.runtime.verification_context import VerificationContext

    policy = build_verification_policy(
        repo_path,
        code_changes=ctx.execution.code_changes,
        user_query=ctx.request.user_query,
    )
    updated = ctx.with_verification(
        VerificationContext(
            test_results=ctx.verification.test_results,
            reviewer_feedback=ctx.verification.reviewer_feedback,
            checks_required=policy.checks_required,
            policy_reason=policy.reason,
            harness=policy.harness.to_dict(),
        )
    )
    return updated, policy


def _verification_passed(tracker: CompletionTracker, *, lint_only: bool) -> bool:
    if tracker.verification_waived:
        return True
    if tracker.tests_succeeded:
        return True
    if lint_only and tracker.lint_succeeded:
        return True
    return False


def _has_apply_in_ctx(ctx: ExecutionContext) -> bool:
    if ctx.execution.code_changes:
        return True
    for entry in ctx.execution.tool_results:
        if isinstance(entry, dict) and entry.get("name") == "executor.apply":
            if entry.get("success"):
                return True
    return False
