"""ExecutionContext immutability and functional updates."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError

import pytest

from src.context.runtime.execution_context import ExecutionContext
from src.context.runtime.planning_context import PlanningContext, PlanTask
from src.context.runtime.request_context import RequestContext


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        request=RequestContext(
            request_id="r1",
            session_id="s1",
            user_query="add caching",
            repo_path="/tmp/repo",
            requesting_agent="planner",
            task_complexity="MEDIUM",
            created_at="2026-01-01T00:00:00Z",
        )
    )


def test_frozen() -> None:
    ctx = _ctx()
    with pytest.raises(FrozenInstanceError):
        ctx.planning = PlanningContext(plan_steps=("a",))  # type: ignore[misc]


def test_with_planning_returns_new_version() -> None:
    ctx = _ctx()
    nxt = ctx.with_planning(PlanningContext(plan_steps=("step1",), current_step=0))
    assert nxt is not ctx
    assert nxt.version == ctx.version + 1
    assert ctx.planning.plan_steps == ()
    assert nxt.planning.plan_steps == ("step1",)


def test_to_dict_json_roundtrip() -> None:
    ctx = _ctx().with_event("started", {"ok": True})
    payload = ctx.to_dict()
    raw = json.dumps(payload)
    assert "add caching" in raw
    assert json.loads(raw)["request"]["user_query"] == "add caching"


def test_checkpoint_is_identity() -> None:
    ctx = _ctx()
    assert ctx.checkpoint() is ctx


def test_planning_context_tracks_task_checklist() -> None:
    ctx = _ctx()
    tasks = (PlanTask(id="1", content="Add endpoint", status="in_progress"),)
    nxt = ctx.with_planning(PlanningContext(tasks=tasks))
    assert ctx.planning.tasks == ()
    assert nxt.planning.tasks == tasks
