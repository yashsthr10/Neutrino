"""Reconciliation table: every old ExecutionContext field has a new home."""

from __future__ import annotations

import pytest

from src.context.runtime.execution_context import ExecutionContext
from src.context.runtime.request_context import RequestContext


@pytest.fixture
def ctx() -> ExecutionContext:
    return ExecutionContext(
        request=RequestContext(
            request_id="r1",
            session_id="s1",
            user_query="q",
            repo_path="/repo",
            requesting_agent="planner",
            task_complexity="SIMPLE",
            created_at="t",
        )
    )


@pytest.mark.parametrize(
    "old_field,getter",
    [
        ("user_query", lambda c: c.request.user_query),
        ("repo_path", lambda c: c.request.repo_path),
        ("task_complexity", lambda c: c.request.task_complexity),
        ("plan_steps", lambda c: c.planning.plan_steps),
        ("current_step", lambda c: c.planning.current_step),
        ("tasks", lambda c: c.planning.tasks),
        ("code_changes", lambda c: c.execution.code_changes),
        ("tool_results", lambda c: c.execution.tool_results),
        ("test_results", lambda c: c.verification.test_results),
        ("reviewer_feedback", lambda c: c.verification.reviewer_feedback),
        ("token_usage_used", lambda c: c.metrics.token_usage_used),
        ("token_usage_budget", lambda c: c.metrics.token_usage_budget),
        ("iteration_count", lambda c: c.execution.iteration_count),
        ("status", lambda c: c.execution.status),
        ("repository", lambda c: c.repository),
        ("conversation", lambda c: c.conversation),
        ("events", lambda c: c.events),
    ],
)
def test_reconciliation_lookup(ctx: ExecutionContext, old_field: str, getter) -> None:
    assert getter(ctx) is not None or getter(ctx) is None  # path exists
    _ = old_field
