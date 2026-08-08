"""Start / cancel / resume control surface over AgentLoop."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from src.agent.events import AgentEvent
from src.agent.loop import AgentLoop, ContextUpdater
from src.agent.policy import AgentPolicy
from src.agent.state import AgentLoopState, AgentResult
from src.context.runtime.execution_context import ExecutionContext
from src.inference.models.request import Message
from src.inference.ports.inference_port import InferencePort
from src.tool_engine.engine import ToolEngine


@dataclass
class AgentController:
    """Thin control wrapper: run, cancel, resume_after_approval."""

    inference: InferencePort
    tool_engine: ToolEngine
    policy: AgentPolicy = field(default_factory=AgentPolicy)
    on_event: Callable[[AgentEvent], None] | None = None
    auto_approve_shell: bool = False

    def __post_init__(self) -> None:
        self._loop = AgentLoop(
            inference=self.inference,
            tool_engine=self.tool_engine,
            policy=self.policy,
            on_event=self.on_event,
            auto_approve_shell=self.auto_approve_shell,
        )
        self._state = AgentLoopState()
        self._messages: list[Message] = []

    @property
    def state(self) -> AgentLoopState:
        return self._state

    @property
    def messages(self) -> list[Message]:
        return self._messages

    def run(
        self,
        *,
        context: ExecutionContext,
        fsm_state: str,
        user_query: str | None = None,
        update_context: ContextUpdater | None = None,
    ) -> AgentResult:
        if not self._messages:
            query = user_query or context.request.user_query
            self._messages = [Message(role="user", content=query)]
        self._state = AgentLoopState()
        result = self._loop.run(
            context=context,
            fsm_state=fsm_state,
            messages=self._messages,
            state=self._state,
            update_context=update_context,
        )
        return result

    def continue_phase(
        self,
        *,
        context: ExecutionContext,
        fsm_state: str,
        update_context: ContextUpdater | None = None,
    ) -> AgentResult:
        """Run another phase using accumulated message history."""
        # Reset terminal status so policy allows continuation
        if self._state.status in {"COMPLETED", "BLOCKED", "FAILED"}:
            self._state.status = "RUNNING"
            self._state.consecutive_failures = 0
        result = self._loop.run(
            context=context,
            fsm_state=fsm_state,
            messages=self._messages,
            state=self._state,
            update_context=update_context,
        )
        return result

    def cancel(self) -> None:
        self._loop.cancel(self._state)

    def resume_after_approval(
        self,
        *,
        context: ExecutionContext,
        fsm_state: str,
        approved: bool,
        update_context: ContextUpdater | None = None,
    ) -> AgentResult:
        return self._loop.resume_after_approval(
            context=context,
            fsm_state=fsm_state,
            messages=self._messages,
            loop_state=self._state,
            approved=approved,
            update_context=update_context,
        )
