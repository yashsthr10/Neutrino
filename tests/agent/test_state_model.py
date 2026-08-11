"""Soft AgentState derivation."""

from __future__ import annotations

from src.agent.state_model import AgentState, derive_agent_state


def test_apply_then_checks_not_required_reaches_verify_finish() -> None:
    state = derive_agent_state(
        AgentState(),
        tool_name="executor.apply",
        success=True,
        apply_succeeded=True,
        checks_required=False,
    )
    assert state.phase == "VERIFY"
    assert "finishing" in state.objective
    assert "final" in state.next_objective


def test_apply_then_tests_success_reaches_verify_finish() -> None:
    state = derive_agent_state(
        AgentState(phase="IMPLEMENT"),
        tool_name="tests.run",
        success=True,
        apply_succeeded=True,
        checks_required=True,
        tests_succeeded=True,
    )
    assert state.phase == "VERIFY"
    assert "finishing" in state.objective


def test_apply_then_lint_success_without_ctx_flag() -> None:
    state = derive_agent_state(
        AgentState(phase="IMPLEMENT"),
        tool_name="lint.run",
        success=True,
        apply_succeeded=True,
        checks_required=True,
        lint_succeeded=False,
    )
    assert state.phase == "VERIFY"
    assert "finishing" in state.objective


def test_apply_with_checks_required_stays_implement() -> None:
    state = derive_agent_state(
        AgentState(),
        tool_name="executor.apply",
        success=True,
        apply_succeeded=True,
        checks_required=True,
    )
    assert state.phase == "IMPLEMENT"
    assert "Verify" in state.next_objective


def test_verification_failure_after_apply_is_repair() -> None:
    state = derive_agent_state(
        AgentState(phase="IMPLEMENT"),
        tool_name="tests.run",
        success=False,
        apply_succeeded=True,
        checks_required=True,
        verification_failed=True,
    )
    assert state.phase == "REPAIR"
