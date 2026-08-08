"""WorkflowController transition tests."""

from __future__ import annotations

from src.orchestrator.workflow import WorkflowController


def test_plan_to_execute_on_final() -> None:
    wf = WorkflowController()
    wf.start()
    assert wf.fsm_state == "PLAN"
    tr = wf.after_agent_result(agent_final=True)
    assert tr == ("PLAN", "EXECUTE")
    assert wf.fsm_state == "EXECUTE"


def test_plan_to_execute_after_context_resolve() -> None:
    wf = WorkflowController()
    wf.start()
    wf.record_tool("context.resolve", success=True)
    tr = wf.after_agent_result(agent_final=True)
    assert tr == ("PLAN", "EXECUTE")


def test_execute_to_verify_requires_apply() -> None:
    wf = WorkflowController()
    wf.start()
    wf.after_agent_result(agent_final=True)
    assert wf.after_agent_result(agent_final=True) is None
    wf.record_tool("executor.apply", success=True)
    tr = wf.after_agent_result(agent_final=True)
    assert tr == ("EXECUTE", "VERIFY")


def test_verify_to_done_requires_tests() -> None:
    wf = WorkflowController()
    wf.fsm_state = "VERIFY"
    wf.record_tool("tests.run", success=True)
    tr = wf.after_agent_result(agent_final=True)
    assert tr == ("VERIFY", "DONE")


def test_verify_to_done_when_waived() -> None:
    wf = WorkflowController()
    wf.fsm_state = "VERIFY"
    wf.mark_verification_waived(True)
    tr = wf.after_agent_result(agent_final=True)
    assert tr == ("VERIFY", "DONE")


def test_verify_lint_only_accepts_lint_run() -> None:
    wf = WorkflowController()
    wf.fsm_state = "VERIFY"
    wf.record_tool("lint.run", success=True)
    tr = wf.after_agent_result(agent_final=True, lint_only=True)
    assert tr == ("VERIFY", "DONE")


def test_verify_regresses_to_execute_when_tests_fail() -> None:
    wf = WorkflowController()
    wf.fsm_state = "VERIFY"
    wf.record_tool("tests.run", success=False)
    tr = wf.after_agent_result(agent_final=True)
    assert tr == ("VERIFY", "EXECUTE")
    # A fresh apply is required before EXECUTE can advance again.
    assert wf.flags.apply_succeeded is False
    assert wf.flags.tests_attempted is False
    assert wf.flags.verify_cycles == 1


def test_verify_regression_is_bounded() -> None:
    wf = WorkflowController(max_verify_cycles=1)
    wf.fsm_state = "VERIFY"
    wf.record_tool("tests.run", success=False)
    assert wf.after_agent_result(agent_final=True) == ("VERIFY", "EXECUTE")

    # Simulate looping back through EXECUTE into VERIFY a second time, still red.
    wf.fsm_state = "VERIFY"
    wf.record_tool("tests.run", success=False)
    assert wf.after_agent_result(agent_final=True) is None


def test_tests_run_failure_clears_stale_success_flag() -> None:
    wf = WorkflowController()
    wf.fsm_state = "VERIFY"
    wf.record_tool("tests.run", success=True)
    wf.record_tool("tests.run", success=False)
    assert wf.flags.tests_succeeded is False
    assert wf.flags.tests_attempted is True
