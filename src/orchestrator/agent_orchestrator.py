"""Real OrchestratorPort — owns ExecutionContext + FSM, drives AgentController."""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from src.agent.controller import AgentController
from src.agent.events import (
    AgentBlocked,
    AgentEvent,
    AgentFailed,
    AgentWaitingUser,
    ModelInvoked,
    ToolCallCompleted,
    ToolCallRequested,
)
from src.agent.policy import AgentPolicy
from src.config.schema import CliRules
from src.context import ConversationManagerPort
from src.context.runtime.conversation_context import Message as ConversationMessage
from src.context.runtime.execution_context import ExecutionContext
from src.context.runtime.execution_state import ExecutionState
from src.context.runtime.planning_context import PlanningContext, PlanTask
from src.context.runtime.request_context import RequestContext
from src.context.runtime.verification_context import VerificationContext
from src.inference.models.request import Message
from src.inference.ports.inference_port import InferencePort
from src.orchestrator.workflow import WorkflowController
from src.ports.orchestrator_port import (
    AgentMessage,
    ApprovalRequest,
    LogLine,
    PhaseMarker,
    RunFinished,
    StateTransition,
    StatusSnapshot,
    TaskItem,
    TaskListUpdated,
    ToolCallEvent,
    UIEvent,
)
from src.tool_engine.engine import ToolEngine
from src.tool_engine.models import ToolResult
from src.verification.harness import VerificationPolicy, build_verification_policy


class AgentOrchestrator:
    """OrchestratorPort implementation backed by AgentLoop + WorkflowController."""

    def __init__(
        self,
        emit: Callable[[UIEvent], None],
        repo_path: Path,
        *,
        inference: InferencePort,
        tool_engine: ToolEngine,
        rules: CliRules | None = None,
        auto_approve: bool = False,
        session_id: str | None = None,
    ) -> None:
        self._emit = emit
        self._repo_path = repo_path.resolve()
        self._inference = inference
        self._tool_engine = tool_engine
        self._rules = rules or CliRules()
        self._auto_approve = auto_approve
        self._session_id = session_id or uuid.uuid4().hex
        self._runtime_mode: Literal["fast", "deep", "auto"] = "fast"
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._approval_event = threading.Event()
        self._approval_approved = False
        self._workflow = WorkflowController(max_verify_cycles=self._rules.max_verify_cycles)
        self._ctx: ExecutionContext | None = None
        self._tokens = 0
        self._last_status: dict[str, Any] = {
            "modeLabel": "FAST (SIMPLE)",
            "tokensUsed": 0,
            "fsmState": "INIT",
            "taskComplexity": "SIMPLE",
        }
        self._controller: AgentController | None = None
        # Durable conversational memory (same instance ContextManager.resolve reads).
        self._conversation: ConversationManagerPort | None = getattr(
            tool_engine.services, "conversation", None
        )

    @property
    def repo_path(self) -> Path:
        return self._repo_path

    # Compatibility with RpcServer accessing _repo_path
    @property
    def _repo_path_prop(self) -> Path:
        return self._repo_path

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return dict(self._last_status)

    def replace_inference(self, inference: InferencePort) -> None:
        """Hot-swap the InferencePort after TUI /model selection.

        Refuses while a run is active so in-flight chats are not torn down.
        """
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("cannot change model while a run is in progress")
            old = self._inference
            self._inference = inference
        close = getattr(old, "close", None)
        if callable(close):
            try:
                close()
            except Exception:  # noqa: BLE001
                pass
        self._emit(LogLine("Inference backend updated for agent runs", level="info"))

    def submit_task(self, user_query: str) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                self._emit(LogLine("A run is already in progress", level="warning"))
                return
            self._approval_event.clear()
            self._thread = threading.Thread(
                target=self._run_task,
                args=(user_query,),
                name="neutrino-agent",
                daemon=True,
            )
            self._thread.start()

    def run_blocking(self, user_query: str) -> None:
        """CLI entry — run the full workflow on the calling thread."""
        self._run_task(user_query)

    def _run_task(self, user_query: str) -> None:
        try:
            self._execute(user_query)
        except Exception as exc:  # noqa: BLE001
            self._emit(LogLine(f"Agent failed: {exc}", level="error"))
            self._emit(RunFinished(ok=False, message=str(exc)))

    def _execute(self, user_query: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._ctx = ExecutionContext(
            request=RequestContext(
                request_id=uuid.uuid4().hex,
                session_id=self._session_id,
                user_query=user_query,
                repo_path=str(self._repo_path),
                requesting_agent="coder",
                task_complexity="SIMPLE" if self._runtime_mode == "fast" else "COMPLEX",
                created_at=now,
            ),
            execution=ExecutionState(status="RUNNING"),
        )
        # Persist the user turn before PLAN so context.resolve can retrieve it.
        self._append_conversation(
            "user",
            user_query,
            metadata={"request_id": self._ctx.request.request_id},
        )
        old, new = self._workflow.start()
        self._emit(StateTransition(old, new))
        self._emit(PhaseMarker(new))
        self._status()

        policy = AgentPolicy(
            max_iterations=self._rules.max_iterations,
            token_budget=self._rules.token_budget,
        )
        controller = AgentController(
            inference=self._inference,
            tool_engine=self._tool_engine,
            policy=policy,
            on_event=self._on_agent_event,
            auto_approve_shell=self._auto_approve,
        )
        self._controller = controller

        # Drive phases until DONE / terminal
        while self._workflow.fsm_state not in {"DONE", "CANCELLED"}:
            fsm = self._workflow.fsm_state
            self._emit(PhaseMarker(fsm))
            self._status()

            if not controller.messages:
                result = controller.run(
                    context=self._ctx,
                    fsm_state=fsm,
                    user_query=user_query,
                    update_context=self._update_context,
                )
            else:
                result = controller.continue_phase(
                    context=self._ctx,
                    fsm_state=fsm,
                    update_context=self._update_context,
                )

            self._ctx = result.context
            self._tokens = controller.state.tokens_used
            self._status()

            if result.status == "WAITING_USER":
                self._emit(
                    ApprovalRequest(
                        request_id=controller.state.pending_approval_id or "approve",
                        summary=controller.state.pending_tool_name or "tool",
                        preview_snippet=str(
                            (controller.state.pending_tool_arguments or {}).get("command", "")
                        ),
                    )
                )
                self._approval_event.wait()
                self._approval_event.clear()
                result = controller.resume_after_approval(
                    context=self._ctx,
                    fsm_state=fsm,
                    approved=self._approval_approved,
                    update_context=self._update_context,
                )
                self._ctx = result.context
                if result.status == "CANCELLED":
                    old, new = self._workflow.cancel()
                    self._emit(StateTransition(old, new))
                    self._emit(RunFinished(ok=False, message="cancelled"))
                    return

            if result.status == "CANCELLED":
                old, new = self._workflow.cancel()
                self._emit(StateTransition(old, new))
                self._emit(RunFinished(ok=False, message="cancelled"))
                return

            if result.status in {"BLOCKED", "FAILED"}:
                err = result.error or result.status
                self._append_conversation(
                    "assistant",
                    err,
                    metadata={"fsm_state": fsm, "outcome": result.status},
                )
                self._emit(
                    AgentMessage(
                        content=err,
                        final=True,
                    )
                )
                self._emit(RunFinished(ok=False, message=err))
                return

            # COMPLETED for this phase — maybe transition
            if result.final_text:
                self._append_conversation(
                    "assistant",
                    result.final_text,
                    metadata={"fsm_state": fsm, "outcome": "COMPLETED"},
                )
                self._emit(AgentMessage(content=result.final_text, final=True))

            lint_only = False
            if fsm == "VERIFY" and self._ctx is not None:
                policy = self._refresh_verification_policy(self._ctx)
                # Waive only when the runtime says checks are unnecessary AND the
                # model did not already run tests.run (a failed attempt still counts).
                if not policy.checks_required and not self._workflow.flags.tests_attempted:
                    self._workflow.mark_verification_waived(True)
                    self._emit(
                        LogLine(
                            f"VERIFY waived ({policy.reason}) — no runnable checks required",
                            level="info",
                        )
                    )
                lint_only = policy.reason == "lint_harness_present"

            transition = self._workflow.after_agent_result(
                agent_final=True, lint_only=lint_only
            )
            if transition is None:
                if fsm == "EXECUTE" and not self._workflow.flags.apply_succeeded:
                    self._emit(
                        LogLine(
                            "EXECUTE finished without a successful executor.apply",
                            level="warning",
                        )
                    )
                    self._emit(RunFinished(ok=False, message="no_apply"))
                    return
                if fsm == "VERIFY" and not self._workflow.verification_passed(
                    lint_only=lint_only
                ):
                    self._emit(
                        LogLine(
                            "VERIFY finished without a successful check "
                            f"after {self._workflow.flags.verify_cycles} retry(ies)",
                            level="warning",
                        )
                    )
                    self._emit(RunFinished(ok=False, message="tests_not_green"))
                    return
                self._emit(RunFinished(ok=False, message="workflow_stuck"))
                return

            old, new = transition
            self._emit(StateTransition(old, new))
            if old == "EXECUTE" and new == "VERIFY" and self._ctx is not None:
                self._refresh_verification_policy(self._ctx)
                self._inject_phase_hint(
                    controller,
                    "FSM advanced to VERIFY. Call verify.probe (or rna.list_files) "
                    "to see available checks. If the runtime policy says checks are "
                    "not required, emit a short final — do not invent tests. "
                    "If rules are required, run tests.run / lint.run (or approved "
                    "executor.run) before your final.",
                )
            if old == "VERIFY" and new == "EXECUTE":
                self._emit(
                    LogLine(
                        "Verification did not pass — returning to EXECUTE "
                        f"(attempt {self._workflow.flags.verify_cycles}/"
                        f"{self._workflow.max_verify_cycles})",
                        level="warning",
                    )
                )
                self._inject_phase_hint(
                    controller,
                    "VERIFY failed or was incomplete. Fix the code with executor.apply. "
                    "Files already created must use Update File / search_replace — "
                    "do not *** Add File for paths that already exist. "
                    "Re-read files if unsure what is on disk.",
                )
            if new == "DONE":
                self._ctx = self._ctx.with_execution(
                    replace(self._ctx.execution, status="DONE")
                )
                self._status()
                self._emit(RunFinished(ok=True, message="done"))
                return

    def _append_conversation(
        self,
        role: Literal["user", "assistant", "system", "tool"],
        content: str,
        *,
        metadata: dict[str, str] | None = None,
    ) -> None:
        """Write a turn into ConversationManagerPort (durable session memory)."""
        if self._conversation is None:
            return
        text = (content or "").strip()
        if not text:
            return
        meta = {"session_id": self._session_id}
        if metadata:
            meta.update({str(k): str(v) for k, v in metadata.items()})
        try:
            self._conversation.append(
                ConversationMessage(
                    role=role,
                    content=text,
                    created_at=datetime.now(timezone.utc).isoformat(),
                    metadata=meta,
                )
            )
        except Exception as exc:  # noqa: BLE001
            # Memory must not fail the agent run.
            self._emit(LogLine(f"Conversation memory append failed: {exc}", level="warning"))

    def _refresh_verification_policy(self, ctx: ExecutionContext) -> VerificationPolicy:
        policy = build_verification_policy(
            self._repo_path,
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
        self._ctx = updated
        return policy

    def _inject_phase_hint(self, controller: AgentController, text: str) -> None:
        """Keep cross-phase awareness in the live message list."""
        controller.messages.append(Message(role="user", content=text))

    def _update_context(
        self,
        ctx: ExecutionContext,
        tool_name: str,
        arguments: dict[str, Any],
        result: ToolResult,
    ) -> ExecutionContext:
        self._workflow.record_tool(tool_name, success=result.success)
        tool_entry = {
            "name": tool_name,
            "arguments": arguments,
            "success": result.success,
            "data": result.data,
            "error": result.meta.error,
        }
        execution = replace(
            ctx.execution,
            tool_results=ctx.execution.tool_results + (tool_entry,),
            iteration_count=ctx.execution.iteration_count + 1,
            status="RUNNING",
        )
        if tool_name == "executor.apply" and result.success and isinstance(result.data, dict):
            changes = result.data.get("changes") or []
            execution = replace(
                execution,
                code_changes=ctx.execution.code_changes + tuple(changes)
                if isinstance(changes, list)
                else ctx.execution.code_changes,
            )
        ctx = ctx.with_execution(execution)
        ctx = ctx.with_event(
            "tool_completed",
            {"name": tool_name, "success": result.success},
        )
        if tool_name == "tests.run":
            ctx = ctx.with_verification(
                VerificationContext(
                    test_results=result.to_dict(),
                    reviewer_feedback=ctx.verification.reviewer_feedback,
                    checks_required=ctx.verification.checks_required,
                    policy_reason=ctx.verification.policy_reason,
                    harness=ctx.verification.harness,
                )
            )
        if tool_name == "verify.probe" and result.success and isinstance(result.data, dict):
            harness = result.data.get("harness")
            ctx = ctx.with_verification(
                VerificationContext(
                    test_results=ctx.verification.test_results,
                    reviewer_feedback=ctx.verification.reviewer_feedback,
                    checks_required=ctx.verification.checks_required,
                    policy_reason=ctx.verification.policy_reason,
                    harness=harness if isinstance(harness, dict) else ctx.verification.harness,
                )
            )
        if tool_name == "plan.set_tasks" and result.success and isinstance(result.data, dict):
            raw_tasks = result.data.get("tasks") or []
            tasks = tuple(
                PlanTask(id=t["id"], content=t["content"], status=t["status"])
                for t in raw_tasks
                if isinstance(t, dict)
            )
            ctx = ctx.with_planning(PlanningContext(tasks=tasks))
            self._emit(
                TaskListUpdated(
                    tuple(TaskItem(id=t.id, content=t.content, status=t.status) for t in tasks)
                )
            )
        self._ctx = ctx
        return ctx

    def _on_agent_event(self, event: AgentEvent) -> None:
        if isinstance(event, ToolCallRequested):
            self._emit(
                ToolCallEvent(
                    name=event.name,
                    args_summary=_args_summary(event.arguments),
                    success=True,
                )
            )
        elif isinstance(event, ToolCallCompleted):
            self._emit(
                ToolCallEvent(
                    name=event.name,
                    args_summary=event.summary,
                    success=event.success,
                )
            )
        elif isinstance(event, AgentBlocked):
            self._emit(LogLine(f"Blocked: {event.reason}", level="warning"))
        elif isinstance(event, AgentFailed):
            self._emit(LogLine(f"Failed: {event.reason}", level="error"))
        elif isinstance(event, AgentWaitingUser):
            self._emit(LogLine(f"Approval required: {event.summary}", level="info"))
        elif isinstance(event, ModelInvoked):
            self._emit(LogLine(f"Model invoked (tools={event.tool_count})", level="info"))

    def _status(self) -> None:
        mode = self._runtime_mode
        if mode == "auto":
            complexity = "AUTO"
            label = "AUTO"
        else:
            complexity = "SIMPLE" if mode == "fast" else "COMPLEX"
            label = f"{mode.upper()} ({complexity})"
        snap = StatusSnapshot(
            mode_label=label,
            tokens_used=self._tokens,
            fsm_state=self._workflow.fsm_state,
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

    def send_approval(self, request_id: str, approved: bool) -> None:
        _ = request_id
        self._approval_approved = approved
        self._approval_event.set()

    def send_approval_action(self, request_id: str, action: str) -> None:
        self.send_approval(request_id, approved=(action == "accept"))

    def submit_approval_edit(self, request_id: str, new_text: str) -> None:
        _ = request_id, new_text
        self.send_approval(request_id, approved=True)

    def set_runtime_mode(self, mode: Literal["fast", "deep", "auto"]) -> None:
        self._runtime_mode = mode
        self._status()

    def request_retry(self) -> None:
        self._emit(LogLine("Retry requested — resubmit the task", level="info"))

    def request_context_refresh(self) -> None:
        self._emit(LogLine("Context refresh requested", level="info"))

    def request_repo_tree(self) -> None:
        paths: list[str] = []
        try:
            for p in sorted(self._repo_path.rglob("*")):
                if p.is_file() and ".git" not in p.parts:
                    rel = p.relative_to(self._repo_path).as_posix()
                    paths.append(rel)
                    if len(paths) >= 200:
                        break
        except OSError:
            pass
        from src.ports.orchestrator_port import RepoTreeSnapshot

        self._emit(RepoTreeSnapshot(root_label=self._repo_path.name, paths=tuple(paths)))

    def select_recovery_option(self, option_id: str) -> None:
        _ = option_id
        self._emit(LogLine("Recovery option selected", level="info"))

    def cancel_run(self) -> None:
        if self._controller is not None:
            self._controller.cancel()
        self._approval_approved = False
        self._approval_event.set()


def _args_summary(arguments: dict[str, Any]) -> str:
    if not arguments:
        return ""
    parts = [f"{k}={v!r}" for k, v in list(arguments.items())[:4]]
    text = ", ".join(parts)
    return text if len(text) <= 160 else text[:157] + "..."
