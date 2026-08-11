"""WorkflowController status façade + CompletionPolicy tests."""

from __future__ import annotations

from pathlib import Path

from src.context.runtime.execution_context import ExecutionContext
from src.context.runtime.execution_state import ExecutionState
from src.context.runtime.request_context import RequestContext
from src.orchestrator.completion import (
    CompletionDecisionKind,
    CompletionTracker,
    evaluate_completion,
)
from src.orchestrator.workflow import WorkflowController


def test_start_enters_agent() -> None:
    wf = WorkflowController()
    old, new = wf.start()
    assert old == "INIT"
    assert new == "AGENT"
    assert wf.fsm_state == "AGENT"


def test_mark_done_and_cancel() -> None:
    wf = WorkflowController()
    wf.start()
    assert wf.mark_done() == ("AGENT", "DONE")
    wf2 = WorkflowController()
    wf2.start()
    assert wf2.cancel() == ("AGENT", "CANCELLED")


def test_record_tool_flags() -> None:
    wf = WorkflowController()
    wf.start()
    wf.record_tool("context.resolve", success=True)
    wf.record_tool("executor.apply", success=True)
    wf.record_tool("tests.run", success=True)
    assert wf.flags.context_resolved
    assert wf.flags.apply_succeeded
    assert wf.flags.tests_succeeded


def _ctx(repo: Path, *, changes: tuple = ()) -> ExecutionContext:
    return ExecutionContext(
        request=RequestContext(
            request_id="r",
            session_id="s",
            user_query="task",
            repo_path=str(repo),
            requesting_agent="coder",
            task_complexity="SIMPLE",
            created_at="2026-01-01T00:00:00Z",
        ),
        execution=ExecutionState(code_changes=changes, status="RUNNING"),
    )


def test_completion_no_writes_is_done(tmp_path: Path) -> None:
    tracker = CompletionTracker()
    decision = evaluate_completion(_ctx(tmp_path), tracker, repo_path=tmp_path, agent_final=True)
    assert decision.kind == CompletionDecisionKind.DONE
    assert decision.reason == "no_writes"


def test_completion_write_without_harness_waives(tmp_path: Path) -> None:
    # Empty repo: no test/lint markers → checks not required for many static-only cases;
    # with a .py change and no harness, policy still may require or waive — seed no markers.
    (tmp_path / "readme.md").write_text("hi", encoding="utf-8")
    tracker = CompletionTracker()
    tracker.apply_succeeded = True
    ctx = _ctx(tmp_path, changes=({"path": "readme.md"},))
    decision = evaluate_completion(ctx, tracker, repo_path=tmp_path, agent_final=True)
    assert decision.kind in {
        CompletionDecisionKind.DONE,
        CompletionDecisionKind.CONTINUE,
    }


def test_completion_needs_verification_when_harness_present(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x=1\n", encoding="utf-8")
    tracker = CompletionTracker()
    tracker.apply_succeeded = True
    ctx = _ctx(tmp_path, changes=({"path": "pkg/mod.py"},))
    decision = evaluate_completion(ctx, tracker, repo_path=tmp_path, agent_final=True)
    assert decision.kind == CompletionDecisionKind.CONTINUE
    assert decision.reason == "need_verification"
    assert tracker.verify_cycles == 1


def test_completion_green_tests_done(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x=1\n", encoding="utf-8")
    tracker = CompletionTracker()
    tracker.apply_succeeded = True
    tracker.tests_succeeded = True
    tracker.tests_attempted = True
    ctx = _ctx(tmp_path, changes=({"path": "pkg/mod.py"},))
    decision = evaluate_completion(ctx, tracker, repo_path=tmp_path, agent_final=True)
    assert decision.kind == CompletionDecisionKind.DONE
    assert decision.reason == "checks_green"


def test_completion_blocked_after_max_cycles(tmp_path: Path) -> None:
    (tmp_path / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("x=1\n", encoding="utf-8")
    tracker = CompletionTracker(max_verify_cycles=1)
    tracker.apply_succeeded = True
    tracker.verify_cycles = 1
    ctx = _ctx(tmp_path, changes=({"path": "pkg/mod.py"},))
    decision = evaluate_completion(ctx, tracker, repo_path=tmp_path, agent_final=True)
    assert decision.kind == CompletionDecisionKind.BLOCKED
    assert decision.reason == "tests_not_green"
