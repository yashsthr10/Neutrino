"""Agent policy guard tests."""

from __future__ import annotations

import time

from src.agent.policy import AgentPolicy
from src.agent.state import AgentLoopState


def test_max_iterations() -> None:
    policy = AgentPolicy(max_iterations=2)
    state = AgentLoopState(status="RUNNING", iteration=2, started_at=time.time())
    ok, reason = policy.should_continue(state)
    assert ok is False
    assert reason == "max_iterations"


def test_same_tool_repetition() -> None:
    policy = AgentPolicy(max_same_tool_repetition=3)
    state = AgentLoopState(status="RUNNING", started_at=time.time())
    for _ in range(3):
        policy.record_tool_outcome(
            state, tool_name="rna.search", arguments={"query": "x"}, success=True
        )
    ok, reason = policy.should_continue(state)
    assert ok is False
    assert reason == "max_same_tool_repetition"


def test_consecutive_failures() -> None:
    policy = AgentPolicy(max_tool_failures=3)
    state = AgentLoopState(status="RUNNING", started_at=time.time())
    for _ in range(3):
        policy.record_tool_outcome(
            state, tool_name="executor.apply", arguments={"patch": "a"}, success=False
        )
    ok, reason = policy.should_continue(state)
    assert ok is False
    assert reason == "max_tool_failures"


def test_cancel_stops() -> None:
    policy = AgentPolicy()
    state = AgentLoopState(status="RUNNING", cancel_requested=True, started_at=time.time())
    ok, reason = policy.should_continue(state)
    assert ok is False
    assert reason == "cancelled"
