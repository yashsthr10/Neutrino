"""Core agent iteration — InferencePort + ToolEngine only."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from src.agent.classifier import classify
from src.agent.events import (
    AgentBlocked,
    AgentCompleted,
    AgentEvent,
    AgentFailed,
    AgentIterationCompleted,
    AgentIterationStarted,
    AgentWaitingUser,
    ModelCompleted,
    ModelInvoked,
    TimingSummary,
    ToolCallCompleted,
    ToolCallRequested,
)
from src.agent.policy import AgentPolicy
from src.agent.prompts.compiler import (
    PromptInputs,
    compile_system_prompt,
    format_reminders_message,
)
from src.agent.reminders import ReminderFacts, build_reminders, looks_question_like, observe_tool
from src.agent.state import AgentLoopState, AgentResult
from src.agent.state_model import AgentState, derive_agent_state
from src.agent.timing import TimingStats
from src.agent.tool_call_repair import (
    extract_failed_generation,
    is_tool_use_failed,
    repair_guidance,
    salvage_tool_calls,
)
from src.context.runtime.execution_context import ExecutionContext
from src.inference.adapters.tool_adapter import tool_engine_schemas_to_specs
from src.inference.errors import ToolUseFailed
from src.inference.models.request import InferenceRequest, Message, ToolCall
from src.inference.ports.inference_port import InferencePort
from src.tool_engine.engine import ToolEngine
from src.tool_engine.models import ToolRequest, ToolResult

EventCallback = Callable[[AgentEvent], None]
ContextUpdater = Callable[[ExecutionContext, str, dict[str, Any], ToolResult], ExecutionContext]

_TOOLS_NEEDING_APPROVAL = frozenset({"executor.run"})


@dataclass
class AgentLoop:
    """LLM-driven decision cycle. Does not own FSM or domain services."""

    inference: InferencePort
    tool_engine: ToolEngine
    policy: AgentPolicy = field(default_factory=AgentPolicy)
    on_event: EventCallback | None = None
    auto_approve_shell: bool = False
    environment: dict[str, Any] | None = None
    agent_state: AgentState | None = None
    reminder_facts: ReminderFacts | None = None
    pending_nudge: str | None = None
    timing: TimingStats = field(default_factory=TimingStats)

    def run(
        self,
        *,
        context: ExecutionContext,
        fsm_state: str,
        messages: list[Message],
        state: AgentLoopState | None = None,
        update_context: ContextUpdater | None = None,
    ) -> AgentResult:
        loop_state = state or AgentLoopState()
        if not loop_state.started_at:
            loop_state.started_at = time.time()
        loop_state.status = "RUNNING"
        ctx = context
        # Mutate the caller's list in place so continuous agent history is preserved.
        history = messages
        final_text: str | None = None
        if self.agent_state is None:
            self.agent_state = AgentState()
        if self.reminder_facts is None:
            self.reminder_facts = ReminderFacts(
                question_like=looks_question_like(ctx.request.user_query),
                max_iterations=self.policy.max_iterations,
                token_budget=self.policy.token_budget,
            )

        while True:
            ok, stop_reason = self.policy.should_continue(loop_state)
            if not ok:
                return self._stop(loop_state, ctx, final_text, stop_reason)

            loop_state.iteration += 1
            self._emit(AgentIterationStarted(loop_state.iteration, fsm_state))
            self.reminder_facts.iteration = loop_state.iteration
            self.reminder_facts.tokens_used = loop_state.tokens_used
            self.reminder_facts.checks_required = ctx.verification.checks_required
            self.reminder_facts.same_tool_streak = int(loop_state.same_tool_streak[1] or 0)

            schemas = self.tool_engine.schemas_for_state(fsm_state)
            tools = tool_engine_schemas_to_specs(schemas)
            request = InferenceRequest(
                messages=tuple(self._with_system(history, fsm_state, ctx)),
                tools=tools,
                tool_choice="auto" if tools else None,
            )
            self._emit(ModelInvoked(loop_state.iteration, len(tools)))

            try:
                t0 = time.perf_counter()
                response = self.inference.chat(request)
                model_ms = (time.perf_counter() - t0) * 1000.0
                self.timing.record_model(
                    model_ms,
                    input_tokens=int(response.usage.input_tokens),
                    output_tokens=int(response.usage.output_tokens),
                )
                self._emit(
                    ModelCompleted(
                        iteration=loop_state.iteration,
                        latency_ms=model_ms,
                        input_tokens=int(response.usage.input_tokens),
                        output_tokens=int(response.usage.output_tokens),
                        tool_count=len(tools),
                    )
                )
            except ToolUseFailed as exc:
                handled, ctx = self._recover_tool_use_failed(
                    exc,
                    history=history,
                    ctx=ctx,
                    fsm_state=fsm_state,
                    loop_state=loop_state,
                    update_context=update_context,
                )
                if handled is not None:
                    return handled
                continue
            except Exception as exc:  # noqa: BLE001
                # Some providers wrap tool_use_failed as a generic connection error.
                if is_tool_use_failed(exc):
                    handled, ctx = self._recover_tool_use_failed(
                        ToolUseFailed(
                            str(exc),
                            failed_generation=extract_failed_generation(exc),
                        ),
                        history=history,
                        ctx=ctx,
                        fsm_state=fsm_state,
                        loop_state=loop_state,
                        update_context=update_context,
                    )
                    if handled is not None:
                        return handled
                    continue
                self._emit(AgentIterationCompleted(loop_state.iteration, "error"))
                loop_state.status = "FAILED"
                self._emit(AgentFailed(str(exc)))
                return self._result(
                    status="FAILED",
                    final_text=None,
                    context=ctx,
                    error=str(exc),
                    fsm_state=fsm_state,
                    emit_timing=True,
                )

            loop_state.tokens_used += int(response.usage.input_tokens) + int(
                response.usage.output_tokens
            )
            outcome = classify(response)

            if outcome.kind == "error":
                loop_state.consecutive_failures += 1
                self._emit(AgentIterationCompleted(loop_state.iteration, "error"))
                if loop_state.consecutive_failures >= self.policy.max_tool_failures:
                    return self._blocked(loop_state, ctx, "inference_errors")
                # Feed error back and continue
                history.append(
                    Message(role="assistant", content=outcome.message or "inference error")
                )
                continue

            if outcome.kind == "invalid":
                loop_state.consecutive_failures += 1
                self._emit(AgentIterationCompleted(loop_state.iteration, "invalid"))
                # If the model leaked XML tool markup into content, try to salvage it.
                if outcome.message == "xml_tool_markup_in_content" and outcome.content:
                    salvaged = salvage_tool_calls(outcome.content)
                    if salvaged:
                        loop_state.consecutive_failures = 0
                        loop_state.status = "WAITING_TOOL"
                        history.append(
                            Message(
                                role="assistant",
                                content=None,
                                tool_calls=salvaged,
                            )
                        )
                        status, ctx, reason = self._execute_tools(
                            salvaged,
                            history=history,
                            ctx=ctx,
                            fsm_state=fsm_state,
                            loop_state=loop_state,
                            update_context=update_context,
                        )
                        history.append(
                            Message(
                                role="user",
                                content=repair_guidance(
                                    salvaged=True, failed_generation=outcome.content
                                ),
                            )
                        )
                        if status == "waiting_user":
                            return self._result(
                                status="WAITING_USER",
                                final_text=None,
                                context=ctx,
                                fsm_state=fsm_state,
                            )
                        if status == "blocked":
                            return self._blocked(loop_state, ctx, reason or "tool_policy")
                        loop_state.status = "RUNNING"
                        continue
                history.append(
                    Message(
                        role="assistant",
                        content=outcome.content or "",
                    )
                )
                guidance = (
                    repair_guidance(salvaged=False, failed_generation=outcome.content)
                    if outcome.message == "xml_tool_markup_in_content"
                    else (
                        "Your previous response was invalid. "
                        "Call a tool via native function calling, or provide a clear final answer. "
                        "Never emit `<tool_call>` / `<function=` XML."
                    )
                )
                history.append(Message(role="user", content=guidance))
                if loop_state.consecutive_failures >= self.policy.max_tool_failures:
                    return self._blocked(loop_state, ctx, "invalid_responses")
                continue

            if outcome.kind == "tool_calls":
                loop_state.consecutive_failures = 0
                loop_state.status = "WAITING_TOOL"
                history.append(
                    Message(
                        role="assistant",
                        content=outcome.content,
                        tool_calls=outcome.tool_calls,
                    )
                )
                status, ctx, reason = self._execute_tools(
                    outcome.tool_calls,
                    history=history,
                    ctx=ctx,
                    fsm_state=fsm_state,
                    loop_state=loop_state,
                    update_context=update_context,
                )
                if status == "waiting_user":
                    self._emit(AgentIterationCompleted(loop_state.iteration, "tool_calls"))
                    return self._result(
                        status="WAITING_USER",
                        final_text=None,
                        context=ctx,
                        fsm_state=fsm_state,
                    )
                if status == "blocked":
                    return self._blocked(loop_state, ctx, reason or "tool_policy")
                if loop_state.cancel_requested:
                    return self._stop(loop_state, ctx, None, "cancelled")
                loop_state.status = "RUNNING"
                self._emit(AgentIterationCompleted(loop_state.iteration, "tool_calls"))
                continue

            # FINAL
            final_text = outcome.content or ""
            history.append(Message(role="assistant", content=final_text))
            loop_state.status = "COMPLETED"
            self._emit(AgentIterationCompleted(loop_state.iteration, "final"))
            self._emit(AgentCompleted(final_text))
            # Timing summary is emitted by the orchestrator on true run end
            # (CompletionPolicy may CONTINUE after a model final).
            return self._result(
                status="COMPLETED",
                final_text=final_text,
                context=ctx,
                fsm_state=fsm_state,
            )

    def resume_after_approval(
        self,
        *,
        context: ExecutionContext,
        fsm_state: str,
        messages: list[Message],
        loop_state: AgentLoopState,
        approved: bool,
        update_context: ContextUpdater | None = None,
    ) -> AgentResult:
        """Continue after WAITING_USER for a gated tool."""
        if not approved:
            loop_state.status = "CANCELLED"
            loop_state.pending_approval_id = None
            return self._result(
                status="CANCELLED",
                final_text=None,
                context=context,
                error="approval_rejected",
                fsm_state=fsm_state,
                emit_timing=True,
            )
        name = loop_state.pending_tool_name
        args = dict(loop_state.pending_tool_arguments or {})
        if not name:
            loop_state.status = "FAILED"
            return self._result(
                status="FAILED",
                final_text=None,
                context=context,
                error="no_pending_approval",
                fsm_state=fsm_state,
                emit_timing=True,
            )
        args["approved"] = True
        loop_state.pending_approval_id = None
        loop_state.pending_tool_name = None
        loop_state.pending_tool_arguments = None
        loop_state.status = "RUNNING"

        result = self.tool_engine.invoke(
            ToolRequest(name=name, arguments=args, execution_context=context),
            state=fsm_state,
        )
        self.timing.record_tool(name, float(result.meta.cost_ms or 0.0))
        self.policy.record_tool_outcome(
            loop_state, tool_name=name, arguments=args, success=result.success
        )
        self._emit(
            ToolCallCompleted(
                name=name,
                success=result.success,
                error=result.meta.error,
                summary=_summarize_result(result),
                cost_ms=float(result.meta.cost_ms or 0.0),
            )
        )
        ctx = context
        if update_context is not None:
            ctx = update_context(ctx, name, args, result)
        messages.append(
            Message(
                role="tool",
                tool_call_id="approved",
                name=name,
                content=json.dumps(result.to_dict(), default=str),
            )
        )
        return self.run(
            context=ctx,
            fsm_state=fsm_state,
            messages=messages,
            state=loop_state,
            update_context=update_context,
        )

    def cancel(self, state: AgentLoopState) -> None:
        state.cancel_requested = True

    def _recover_tool_use_failed(
        self,
        exc: ToolUseFailed,
        *,
        history: list[Message],
        ctx: ExecutionContext,
        fsm_state: str,
        loop_state: AgentLoopState,
        update_context: ContextUpdater | None,
    ) -> tuple[AgentResult | None, ExecutionContext]:
        """Salvage or retry after Groq-style ``tool_use_failed``.

        Returns ``(AgentResult, ctx)`` when the phase should stop, or
        ``(None, ctx)`` to continue the iteration loop with corrective history.
        """
        failed_gen = exc.failed_generation or extract_failed_generation(exc)
        salvaged = salvage_tool_calls(failed_gen or "")
        self._emit(AgentIterationCompleted(loop_state.iteration, "error"))

        if salvaged:
            loop_state.consecutive_failures = 0
            loop_state.status = "WAITING_TOOL"
            history.append(
                Message(
                    role="assistant",
                    content=None,
                    tool_calls=salvaged,
                )
            )
            status, ctx, reason = self._execute_tools(
                salvaged,
                history=history,
                ctx=ctx,
                fsm_state=fsm_state,
                loop_state=loop_state,
                update_context=update_context,
            )
            history.append(
                Message(
                    role="user",
                    content=repair_guidance(salvaged=True, failed_generation=failed_gen),
                )
            )
            if status == "waiting_user":
                return (
                    self._result(
                        status="WAITING_USER",
                        final_text=None,
                        context=ctx,
                        fsm_state=fsm_state,
                    ),
                    ctx,
                )
            if status == "blocked":
                return self._blocked(loop_state, ctx, reason or "tool_policy"), ctx
            if loop_state.cancel_requested:
                return self._stop(loop_state, ctx, None, "cancelled"), ctx
            loop_state.status = "RUNNING"
            return None, ctx

        loop_state.consecutive_failures += 1
        history.append(
            Message(
                role="assistant",
                content=(failed_gen[:2000] if failed_gen else str(exc))[:2000],
            )
        )
        history.append(
            Message(
                role="user",
                content=repair_guidance(salvaged=False, failed_generation=failed_gen),
            )
        )
        if loop_state.consecutive_failures >= self.policy.max_tool_failures:
            return self._blocked(loop_state, ctx, "tool_use_failed"), ctx
        loop_state.status = "RUNNING"
        return None, ctx

    def _execute_tools(
        self,
        tool_calls: tuple[ToolCall, ...],
        *,
        history: list[Message],
        ctx: ExecutionContext,
        fsm_state: str,
        loop_state: AgentLoopState,
        update_context: ContextUpdater | None,
    ) -> tuple[str, ExecutionContext, str | None]:
        """Returns (status, context, reason) where status is ok|waiting_user|blocked."""
        for tc in tool_calls:
            if loop_state.cancel_requested:
                return "blocked", ctx, "cancelled"
            try:
                args = json.loads(tc.arguments) if tc.arguments else {}
                if not isinstance(args, dict):
                    args = {"_raw": tc.arguments}
            except json.JSONDecodeError:
                args = {"_raw": tc.arguments}

            self._emit(ToolCallRequested(name=tc.name, arguments=args, tool_call_id=tc.id))

            if tc.name in _TOOLS_NEEDING_APPROVAL and not args.get("approved"):
                if self.auto_approve_shell:
                    args = {**args, "approved": True}
                else:
                    request_id = tc.id or f"approve-{loop_state.iteration}"
                    loop_state.status = "WAITING_USER"
                    loop_state.pending_approval_id = request_id
                    loop_state.pending_tool_name = tc.name
                    loop_state.pending_tool_arguments = args
                    self._emit(
                        AgentWaitingUser(
                            request_id=request_id,
                            tool_name=tc.name,
                            summary=str(args.get("command") or tc.name),
                        )
                    )
                    return "waiting_user", ctx, None

            result = self.tool_engine.invoke(
                ToolRequest(name=tc.name, arguments=args, execution_context=ctx),
                state=fsm_state,
            )
            self.policy.record_tool_outcome(
                loop_state, tool_name=tc.name, arguments=args, success=result.success
            )
            err_text = result.meta.error or ("; ".join(result.errors) if result.errors else "")
            if self.reminder_facts is not None:
                observe_tool(
                    self.reminder_facts,
                    name=tc.name,
                    success=result.success,
                    error_text=err_text,
                    same_tool_streak=int(loop_state.same_tool_streak[1] or 0),
                )
            if self.agent_state is not None:
                open_tasks = any(
                    getattr(t, "status", "") in {"pending", "in_progress"}
                    for t in ctx.planning.tasks
                )
                self.agent_state = derive_agent_state(
                    self.agent_state,
                    tool_name=tc.name,
                    success=result.success,
                    apply_succeeded=(
                        self.reminder_facts.apply_succeeded if self.reminder_facts else False
                    ),
                    checks_required=ctx.verification.checks_required,
                    tests_succeeded=bool(
                        isinstance(ctx.verification.test_results, dict)
                        and ctx.verification.test_results.get("success")
                    ),
                    has_open_plan_tasks=open_tasks,
                    verification_failed=(
                        tc.name in {"tests.run", "lint.run"} and not result.success
                    ),
                )
            cost_ms = float(result.meta.cost_ms or 0.0)
            self.timing.record_tool(tc.name, cost_ms)
            self._emit(
                ToolCallCompleted(
                    name=tc.name,
                    success=result.success,
                    error=result.meta.error,
                    summary=_summarize_result(result),
                    cost_ms=cost_ms,
                )
            )
            if result.meta.error == "permission_denied" or (
                isinstance(result.data, dict) and result.data.get("needs_approval")
            ):
                if not self.auto_approve_shell:
                    request_id = tc.id or f"approve-{loop_state.iteration}"
                    loop_state.status = "WAITING_USER"
                    loop_state.pending_approval_id = request_id
                    loop_state.pending_tool_name = tc.name
                    loop_state.pending_tool_arguments = args
                    self._emit(
                        AgentWaitingUser(
                            request_id=request_id,
                            tool_name=tc.name,
                            summary=str(args.get("command") or tc.name),
                        )
                    )
                    return "waiting_user", ctx, None

            if update_context is not None:
                ctx = update_context(ctx, tc.name, args, result)

            history.append(
                Message(
                    role="tool",
                    tool_call_id=tc.id,
                    name=tc.name,
                    content=json.dumps(result.to_dict(), default=str),
                )
            )

            # Temporarily treat as RUNNING so policy streak/failure checks apply
            prev_status = loop_state.status
            loop_state.status = "RUNNING"
            ok, reason = self.policy.should_continue(loop_state)
            loop_state.status = prev_status
            if not ok and reason in {
                "max_tool_failures",
                "max_same_tool_repetition",
                "token_budget",
                "max_runtime_seconds",
                "max_iterations",
            }:
                return "blocked", ctx, reason

        return "ok", ctx, None

    def _with_system(
        self, history: list[Message], fsm_state: str, ctx: ExecutionContext
    ) -> list[Message]:
        _ = fsm_state
        tool_specs = self.tool_engine.list_tools(fsm_state)
        reminders = build_reminders(self.reminder_facts) if self.reminder_facts else ()
        nudge = (self.pending_nudge or "").strip()
        if nudge:
            reminders = (*reminders, nudge)
            self.pending_nudge = None
        repo_items = ()
        if ctx.repository is not None:
            repo_items = ctx.repository.items
        compiled = compile_system_prompt(
            PromptInputs(
                user_query=ctx.request.user_query,
                repo_path=ctx.request.repo_path,
                tools=tool_specs,
                environment=self.environment or {"repo_path": ctx.request.repo_path},
                agent_state=self.agent_state,
                task_complexity=ctx.request.task_complexity,
                code_changes=ctx.execution.code_changes,
                plan_tasks=ctx.planning.tasks,
                repository_items=repo_items,
                checks_required=ctx.verification.checks_required,
                policy_reason=ctx.verification.policy_reason,
                harness=ctx.verification.harness,
                test_results=ctx.verification.test_results,
                reminders=reminders,
            )
        )
        body = list(history)
        # System is request-local: never persist into controller history.
        if body and body[0].role == "system":
            body = body[1:]
        out: list[Message] = [Message(role="system", content=compiled.system), *body]
        reminder_msg = format_reminders_message(compiled.reminders)
        if reminder_msg:
            out.append(Message(role="user", content=reminder_msg))
        return out

    def _emit(self, event: AgentEvent) -> None:
        if self.on_event is not None:
            self.on_event(event)

    def _emit_timing_summary(self) -> None:
        if self.timing.model_calls == 0 and self.timing.tool_calls == 0:
            return
        self._emit(
            TimingSummary(
                lines=tuple(self.timing.summary_lines()),
                stats=self.timing.to_dict(),
            )
        )

    def _result(
        self,
        *,
        status: str,
        final_text: str | None,
        context: ExecutionContext,
        error: str | None = None,
        fsm_state: str = "INIT",
        emit_timing: bool = False,
    ) -> AgentResult:
        if emit_timing:
            self._emit_timing_summary()
        return AgentResult(
            status=status,  # type: ignore[arg-type]
            final_text=final_text,
            context=context,
            error=error,
            fsm_state=fsm_state,
            timing=self.timing.to_dict(),
        )

    def _stop(
        self,
        loop_state: AgentLoopState,
        ctx: ExecutionContext,
        final_text: str | None,
        reason: str | None,
    ) -> AgentResult:
        if reason == "cancelled" or loop_state.cancel_requested:
            loop_state.status = "CANCELLED"
            return self._result(
                status="CANCELLED",
                final_text=final_text,
                context=ctx,
                error="cancelled",
                emit_timing=True,
            )
        if reason in {
            "max_iterations",
            "max_tool_failures",
            "max_same_tool_repetition",
            "max_runtime_seconds",
            "token_budget",
        }:
            return self._blocked(loop_state, ctx, reason or "policy")
        if loop_state.status == "COMPLETED":
            return self._result(
                status="COMPLETED",
                final_text=final_text,
                context=ctx,
                emit_timing=True,
            )
        loop_state.status = "FAILED"
        self._emit(AgentFailed(reason or "stopped"))
        return self._result(
            status="FAILED",
            final_text=final_text,
            context=ctx,
            error=reason,
            emit_timing=True,
        )

    def _blocked(
        self, loop_state: AgentLoopState, ctx: ExecutionContext, reason: str
    ) -> AgentResult:
        loop_state.status = "BLOCKED"
        self._emit(AgentBlocked(reason))
        return self._result(
            status="BLOCKED",
            final_text=None,
            context=ctx,
            error=reason,
            emit_timing=True,
        )


def _summarize_result(result: ToolResult) -> str:
    if result.success:
        return "ok"
    if result.errors:
        return "; ".join(result.errors)[:200]
    return result.meta.error or "failed"
