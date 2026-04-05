"""Fake orchestrator for UI development: emits scripted UIEvent streams."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Literal

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


class FakeOrchestratorPort:
    """Emits events on a background thread; uses injectable emit into Textual."""

    def __init__(
        self,
        emit: Callable[[UIEvent], None],
        repo_path: Path,
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
        self._emit(
            StatusSnapshot(
                mode_label=label,
                tokens_used=tok,
                fsm_state=st,
                task_complexity=complexity,
            )
        )

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
        self._emit(LogLine("Cancel requested (fake run will stop between steps).", "warning"))
        self._approval_event.set()
        self._recovery_event.set()

    def _sleep_step(self, sec: float) -> bool:
        """Return False if cancelled."""
        with self._lock:
            if self._cancel_requested:
                return False
        time.sleep(sec)
        with self._lock:
            return not self._cancel_requested

    def submit_task(self, user_query: str) -> None:
        def run() -> None:
            with self._lock:
                self._cancel_requested = False

            self._emit(PhaseMarker("PLAN"))
            self._set_state("PLAN")
            self._bump_tokens(50)
            if not self._sleep_step(0.08):
                return

            plan_lines = [
                "Analyzing repository layout…",
                "Identifying affected modules…",
                "Drafting approach for null-safety…",
            ]
            for line in plan_lines:
                self._emit(ThinkingDelta("PLAN", line, append_newline=True))
                if not self._sleep_step(0.12):
                    return
            self._emit(PhaseStepComplete("PLAN", "plan ready"))
            self._bump_tokens(120)
            if not self._sleep_step(0.08):
                return

            self._emit(
                ReasoningBlock(
                    "Consider edge cases for null inputs and preserve API compatibility.",
                    collapsed_default=True,
                )
            )
            self._emit(
                ExplanationAvailable(
                    (
                        "Null checks align with defensive style used elsewhere.",
                        "Keeps public parse() contract unchanged for non-None callers.",
                    )
                )
            )

            self._emit(PhaseMarker("EXECUTE"))
            self._set_state("EXECUTE")
            self._emit(ToolCallEvent("read_file", "parser.py", True))
            self._bump_tokens(80)
            if not self._sleep_step(0.08):
                return
            self._emit(
                AgentMessage(
                    "Drafting patch: add explicit null checks before dereference.",
                    final=False,
                )
            )
            if not self._sleep_step(0.06):
                return
            self._emit(
                DiffChunk(
                    path="src/parser.py",
                    old_text="def parse(s):\n    return s.strip().split()\n",
                    new_text=(
                        "def parse(s):\n"
                        "    if s is None:\n"
                        "        return []\n"
                        "    return s.strip().split()\n"
                    ),
                )
            )
            self._bump_tokens(200)
            if not self._sleep_step(0.1):
                return

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
            self._recovery_event.clear()
            self._recovery_choice = None
            self._recovery_event.wait(timeout=120.0)
            with self._lock:
                choice = self._recovery_choice
            self._emit(LogLine(f"Recovery option selected: {choice!r}", "info"))

            req_id = str(uuid.uuid4())[:8]
            preview = (
                "--- a/src/parser.py\n+++ b/src/parser.py\n@@ -1,2 +1,5 @@\n"
                " def parse(s):\n+    if s is None:\n+        return []\n"
            )
            self._approval_event.clear()
            self._approval_action = None
            self._emit(
                ApprovalRequest(
                    req_id,
                    "Apply patch to src/parser.py?",
                    preview_snippet=preview,
                    full_file_text="# full file placeholder\n",
                )
            )
            self._approval_event.wait(timeout=120.0)
            with self._lock:
                action = self._approval_action
            self._emit(LogLine(f"Approval action: {action!r}", "info"))
            if action == "reject":
                self._set_state("DONE")
                self._emit(RunFinished(False, "User rejected changes."))
                return
            if action == "view":
                self._emit(LogLine("(fake) Viewed full file in UI.", "info"))

            self._emit(PhaseMarker("VERIFY"))
            self._set_state("VERIFY")
            self._emit(ToolCallEvent("run_tests", "pytest -q", True))
            self._bump_tokens(100)
            if not self._sleep_step(0.08):
                return
            self._emit(LogLine("Tests passed.", "info"))

            self._emit(PhaseMarker("REVIEW"))
            self._set_state("REVIEW")
            self._bump_tokens(60)
            if not self._sleep_step(0.06):
                return
            self._emit(AgentMessage("Change looks good; null handling is explicit.", final=True))

            self._set_state("DONE")
            self._emit(RunFinished(True, f"Completed task: {user_query[:60]}"))

        threading.Thread(target=run, daemon=True).start()

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
                f"Submit approval edit {request_id} ({len(new_text)} chars) (fake: accepted)",
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
        self._emit(LogLine("Retry requested (fake: no-op re-run).", "warning"))
        self.submit_task("(retry)")

    def request_context_refresh(self) -> None:
        self._emit(LogLine("Context refresh requested (fake).", "info"))
        self._bump_tokens(10)
        files = (
            ContextFileInfo("src/parser.py", 120),
            ContextFileInfo("src/main.py", 340),
        )
        edges = (ContextEdge("src/main.py", "src/parser.py"),)
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
        paths: list[str] = []
        try:
            for p in sorted(self._repo_path.rglob("*")):
                if p.is_dir() and p.name.startswith("."):
                    continue
                rel = p.relative_to(self._repo_path)
                paths.append(str(rel))
                if len(paths) > 200:
                    break
        except OSError:
            paths = ["<unreadable>"]
        self._emit(RepoTreeSnapshot(str(self._repo_path), tuple(paths[:200])))
