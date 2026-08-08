"""Dummy streaming orchestrator for Ink TUI development (no LLM / RNA)."""

from __future__ import annotations

import random
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

from src.ports.orchestrator_port import (
    AgentMessage,
    ApprovalRequest,
    ContextEdge,
    ContextFileInfo,
    ContextSummary,
    DiffChunk,
    ExplanationAvailable,
    FailureRecovery,
    LogLine,
    PhaseMarker,
    PhaseStepComplete,
    ReasoningBlock,
    RepoTreeSnapshot,
    RunFinished,
    StateTransition,
    StatusSnapshot,
    ThinkingDelta,
    TokenUpdate,
    ToolCallEvent,
    UIEvent,
)


class DummyOrchestrator:
    """Scripted + lightly randomized UIEvent stream implementing OrchestratorPort."""

    def __init__(
        self,
        emit: Callable[[UIEvent], None],
        repo_path: Path,
        *,
        auto_approve: bool = True,
        auto_recover: bool = True,
    ) -> None:
        self._emit = emit
        self._repo_path = repo_path.resolve()
        self._runtime_mode: Literal["fast", "deep", "auto"] = "fast"
        self._tokens = 0
        self._fsm_state = "INIT"
        self._lock = threading.Lock()
        self._cancel_requested = False
        self._approval_event = threading.Event()
        self._approval_action: str | None = None
        self._recovery_event = threading.Event()
        self._recovery_choice: str | None = None
        self._auto_approve = auto_approve
        self._auto_recover = auto_recover
        self._last_status: dict[str, Any] = {
            "modeLabel": "FAST (SIMPLE)",
            "tokensUsed": 0,
            "fsmState": "INIT",
            "taskComplexity": "SIMPLE",
        }
        self._current_task: str | None = None

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last_status)

    def _set_state(self, s: str) -> None:
        with self._lock:
            old = self._fsm_state
            self._fsm_state = s
        self._emit(StateTransition(old, s))
        self._status()

    def _status(self) -> None:
        with self._lock:
            mode = self._runtime_mode
            tok = self._tokens
            st = self._fsm_state
        if mode == "auto":
            complexity = "AUTO"
            label = "AUTO"
        else:
            complexity = "SIMPLE" if mode == "fast" else "COMPLEX"
            label = f"{mode.upper()} ({complexity})"
        snap = StatusSnapshot(
            mode_label=label,
            tokens_used=tok,
            fsm_state=st,
            task_complexity=complexity,
        )
        with self._lock:
            self._last_status = {
                "modeLabel": snap.mode_label,
                "tokensUsed": snap.tokens_used,
                "fsmState": snap.fsm_state,
                "taskComplexity": snap.task_complexity,
            }
        self._emit(snap)

    def _bump_tokens(self, n: int) -> None:
        with self._lock:
            self._tokens += n
            t = self._tokens
        self._emit(TokenUpdate(used=t, budget=100_000))

    def set_runtime_mode(self, mode: Literal["fast", "deep", "auto"]) -> None:
        with self._lock:
            self._runtime_mode = mode
        self._emit(LogLine(f"Runtime mode set to {mode}", "info"))
        self._status()

    def cancel_run(self) -> None:
        with self._lock:
            self._cancel_requested = True
        self._emit(LogLine("Cancel requested.", "warning"))
        self._approval_event.set()
        self._recovery_event.set()

    def _sleep_step(self, sec: float) -> bool:
        with self._lock:
            if self._cancel_requested:
                return False
        # Light jitter so streams feel less robotic
        time.sleep(sec + random.uniform(0.0, 0.04))
        with self._lock:
            return not self._cancel_requested

    def submit_task(self, user_query: str) -> None:
        def run() -> None:
            with self._lock:
                self._cancel_requested = False
                self._current_task = user_query

            self._emit(LogLine(f"Execution started: {user_query[:80]}", "info"))
            self._emit(PhaseMarker("PLAN"))
            self._set_state("PLAN")
            self._bump_tokens(40 + random.randint(0, 30))
            if not self._sleep_step(0.06):
                self._finish_cancelled()
                return

            plan_lines = [
                "Analyzing repository layout…",
                "Identifying affected modules…",
                f"Drafting approach for: {user_query[:40]}…",
                random.choice(
                    [
                        "Scoring constraint graph branches…",
                        "Selecting cheapest safe path…",
                        "Checking prior decisions…",
                    ]
                ),
            ]
            for line in plan_lines:
                self._emit(ThinkingDelta("PLAN", line, append_newline=True))
                if not self._sleep_step(0.08):
                    self._finish_cancelled()
                    return
            self._emit(PhaseStepComplete("PLAN", "plan ready"))
            self._bump_tokens(80 + random.randint(0, 40))

            self._emit(PhaseMarker("CONTEXT"))
            self._set_state("CONTEXT")
            self._emit(ThinkingDelta("CONTEXT", "Resolving symbols and imports…", True))
            if not self._sleep_step(0.08):
                self._finish_cancelled()
                return
            self.request_context_refresh()
            self._emit(PhaseStepComplete("CONTEXT", "context built"))
            self._emit(LogLine("Context retrieved", "info"))

            self._emit(
                ReasoningBlock(
                    "Prefer diff-based edits; keep public APIs stable.",
                    collapsed_default=True,
                )
            )
            self._emit(
                ExplanationAvailable(
                    (
                        "Touches auth and gateway modules.",
                        "Verification will run unit tests after patch.",
                    )
                )
            )

            self.request_repo_tree()

            self._emit(PhaseMarker("EXECUTE"))
            self._set_state("EXECUTE")
            self._emit(ToolCallEvent("read_file", "auth/service.py", True))
            self._bump_tokens(60)
            if not self._sleep_step(0.06):
                self._finish_cancelled()
                return
            self._emit(
                AgentMessage(
                    "Applying SEARCH/REPLACE on auth service…",
                    final=False,
                )
            )
            self._emit(ThinkingDelta("EXECUTE", "Writing IdentityService…", True))
            if not self._sleep_step(0.06):
                self._finish_cancelled()
                return
            self._emit(
                DiffChunk(
                    path="auth/service.py",
                    old_text="class AuthService:\n    pass\n",
                    new_text="class IdentityService:\n    def authenticate(self, token: str) -> bool:\n        return bool(token)\n",
                )
            )
            self._emit(LogLine("Editing auth/service.py", "info"))
            self._bump_tokens(150 + random.randint(0, 50))

            # Optional recovery gate (auto by default for headless demos)
            self._emit(
                FailureRecovery(
                    "Simulated tool flake: formatter exited with code 1.",
                    (
                        ("auto_fix", "[1] Auto-fix"),
                        ("retry", "[2] Retry step"),
                        ("skip", "[3] Skip"),
                    ),
                )
            )
            if self._auto_recover:
                self.select_recovery_option("auto_fix")
            else:
                self._recovery_event.clear()
                self._recovery_choice = None
                self._recovery_event.wait(timeout=120.0)
            with self._lock:
                if self._cancel_requested:
                    self._finish_cancelled()
                    return
                choice = self._recovery_choice
            self._emit(LogLine(f"Recovery option selected: {choice!r}", "info"))

            req_id = str(uuid.uuid4())[:8]
            preview = (
                "--- a/auth/service.py\n+++ b/auth/service.py\n"
                "-class AuthService\n+class IdentityService\n"
            )
            self._approval_event.clear()
            self._approval_action = None
            self._emit(
                ApprovalRequest(
                    req_id,
                    "Apply patch to auth/service.py?",
                    preview_snippet=preview,
                    full_file_text="class IdentityService:\n    pass\n",
                )
            )
            if self._auto_approve:
                self.send_approval_action(req_id, "accept")
            else:
                self._approval_event.wait(timeout=120.0)
            with self._lock:
                if self._cancel_requested:
                    self._finish_cancelled()
                    return
                action = self._approval_action
            self._emit(LogLine(f"Approval action: {action!r}", "info"))
            if action == "reject":
                self._set_state("DONE")
                self._emit(RunFinished(False, "User rejected changes."))
                return

            self._emit(PhaseMarker("VERIFY"))
            self._set_state("VERIFY")
            self._emit(ToolCallEvent("run_tests", "pytest -q", True))
            self._bump_tokens(90)
            if not self._sleep_step(0.08):
                self._finish_cancelled()
                return
            self._emit(LogLine("Tests passed", "info"))
            self._emit(PhaseStepComplete("VERIFY", "verification complete"))

            self._emit(PhaseMarker("REVIEW"))
            self._set_state("REVIEW")
            self._bump_tokens(40)
            if not self._sleep_step(0.05):
                self._finish_cancelled()
                return
            self._emit(AgentMessage("Change looks good; IdentityService is in place.", final=True))
            self._emit(LogLine("Review approved", "info"))

            self._set_state("DONE")
            self._emit(RunFinished(True, f"Completed task: {user_query[:60]}"))

        threading.Thread(target=run, daemon=True).start()

    def _finish_cancelled(self) -> None:
        self._set_state("CANCELLED")
        self._emit(RunFinished(False, "Cancelled."))

    def send_approval(self, request_id: str, approved: bool) -> None:
        with self._lock:
            self._approval_action = "accept" if approved else "reject"
        self._emit(LogLine(f"Approval {request_id}: {'yes' if approved else 'no'}", "info"))
        self._approval_event.set()

    def send_approval_action(self, request_id: str, action: str) -> None:
        with self._lock:
            self._approval_action = action
        self._emit(LogLine(f"Approval action {request_id}: {action}", "info"))
        self._approval_event.set()

    def submit_approval_edit(self, request_id: str, new_text: str) -> None:
        self._emit(
            LogLine(
                f"Submit approval edit {request_id} ({len(new_text)} chars)",
                "info",
            )
        )
        with self._lock:
            self._approval_action = "accept"
        self._approval_event.set()

    def select_recovery_option(self, option_id: str) -> None:
        with self._lock:
            self._recovery_choice = option_id
        self._emit(LogLine(f"Recovery option {option_id}", "info"))
        self._recovery_event.set()

    def request_retry(self) -> None:
        self._emit(LogLine("Retry requested.", "warning"))
        self.submit_task("(retry)")

    def request_context_refresh(self) -> None:
        self._emit(LogLine("Context refresh requested.", "info"))
        self._bump_tokens(10)
        files = (
            ContextFileInfo("auth/service.py", 120),
            ContextFileInfo("gateway/router.py", 340),
            ContextFileInfo("tests/test_auth.py", 80),
        )
        edges = (ContextEdge("gateway/router.py", "auth/service.py"),)
        with self._lock:
            tok = self._tokens
        self._emit(
            ContextSummary(
                files=files,
                edges=edges,
                tokens_used=tok,
                token_budget=100_000,
            )
        )

    def request_repo_tree(self) -> None:
        paths: list[str] = [
            "auth/",
            "auth/service.py",
            "gateway/",
            "gateway/router.py",
            "models/",
            "tests/",
            "tests/test_auth.py",
        ]
        try:
            for p in sorted(self._repo_path.iterdir()):
                if p.name.startswith("."):
                    continue
                rel = p.name + ("/" if p.is_dir() else "")
                if rel not in paths:
                    paths.append(rel)
                if len(paths) > 40:
                    break
        except OSError:
            pass
        self._emit(RepoTreeSnapshot(self._repo_path.name, tuple(paths[:40])))

    def undo(self) -> None:
        self._emit(LogLine("Undo is a stub in the dummy backend.", "warning"))
