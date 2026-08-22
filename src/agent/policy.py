"""Loop guards — iteration, failure, repetition, time, token budget."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass

from src.config.constants import DEFAULT_MAX_ITERATIONS, DEFAULT_TOKEN_BUDGET
from src.agent.state import AgentLoopState


@dataclass(frozen=True, slots=True)
class AgentPolicy:
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    max_tool_failures: int = 3
    max_same_tool_repetition: int = 3
    max_runtime_seconds: float = 1800.0
    token_budget: int = DEFAULT_TOKEN_BUDGET

    def should_continue(self, state: AgentLoopState) -> tuple[bool, str | None]:
        if state.cancel_requested:
            return False, "cancelled"
        if state.status in {"COMPLETED", "BLOCKED", "FAILED", "CANCELLED", "WAITING_USER"}:
            return False, state.status.lower()
        if state.iteration >= self.max_iterations:
            return False, "max_iterations"
        if state.consecutive_failures >= self.max_tool_failures:
            return False, "max_tool_failures"
        name, count = state.same_tool_streak
        if name and count >= self.max_same_tool_repetition:
            return False, "max_same_tool_repetition"
        if state.started_at and (time.time() - state.started_at) >= self.max_runtime_seconds:
            return False, "max_runtime_seconds"
        if state.tokens_used >= self.token_budget:
            return False, "token_budget"
        return True, None

    def record_tool_outcome(
        self,
        state: AgentLoopState,
        *,
        tool_name: str,
        arguments: dict,
        success: bool,
    ) -> AgentLoopState:
        key = _tool_key(tool_name, arguments)
        prev_key, prev_count = state.same_tool_streak
        streak = (key, prev_count + 1) if key == prev_key else (key, 1)
        failures = 0 if success else state.consecutive_failures + 1
        state.same_tool_streak = streak
        state.consecutive_failures = failures
        return state


def _tool_key(tool_name: str, arguments: dict) -> str:
    raw = json.dumps({"name": tool_name, "arguments": arguments}, sort_keys=True, default=str)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return f"{tool_name}:{digest}"
