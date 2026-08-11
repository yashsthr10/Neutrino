"""Compatibility wrappers around the L1–L6 prompt compiler.

Prefer ``compile_system_prompt`` / ``PromptInputs`` for new code.
"""

from __future__ import annotations

from typing import Any

from src.agent.prompts.compiler import PromptInputs, compile_system_prompt
from src.agent.prompts.layers.task_context import render_task_context
from src.tool_engine.state_policy import allowed_tools, normalize_state
from src.tool_engine.tools import all_tool_specs


def build_system_prompt(
    *,
    fsm_state: str,
    user_query: str,
    repo_path: str,
    execution_snapshot: str | None = None,
    tools: list[Any] | tuple[Any, ...] | None = None,
    environment: dict[str, Any] | None = None,
    agent_state: Any | None = None,
    task_complexity: str | None = None,
    code_changes: tuple[dict, ...] | list[dict] = (),
    plan_tasks: tuple[Any, ...] | list[Any] = (),
    repository_items: tuple[Any, ...] | list[Any] = (),
    checks_required: bool | None = None,
    policy_reason: str | None = None,
    harness: dict[str, Any] | None = None,
    test_results: dict[str, Any] | None = None,
) -> str:
    """Compose the system message for one agent iteration."""
    state = normalize_state(fsm_state)
    if tools is None:
        allow = allowed_tools(state)
        tools = [s for s in all_tool_specs() if s.name in allow and s.enabled]
    compiled = compile_system_prompt(
        PromptInputs(
            user_query=user_query,
            repo_path=repo_path,
            tools=tools,
            environment=environment or {"repo_path": repo_path},
            agent_state=agent_state,
            task_complexity=task_complexity,
            code_changes=code_changes,
            plan_tasks=plan_tasks,
            repository_items=repository_items,
            checks_required=checks_required,
            policy_reason=policy_reason,
            harness=harness,
            test_results=test_results,
        )
    )
    text = compiled.system
    if execution_snapshot and execution_snapshot.strip():
        # Legacy callers may still pass a preformatted snapshot block.
        text = text.rstrip() + "\n\n" + execution_snapshot.strip() + "\n"
    return text


def format_execution_snapshot(
    *,
    code_changes: tuple[dict, ...] | list[dict] = (),
    checks_required: bool | None = None,
    policy_reason: str | None = None,
    harness: dict[str, Any] | None = None,
    test_results: dict[str, Any] | None = None,
) -> str:
    """Compact runtime facts (kept for orchestrator / tests)."""
    return render_task_context(
        user_query="",
        code_changes=code_changes,
        checks_required=checks_required,
        policy_reason=policy_reason,
        harness=harness,
        test_results=test_results,
    ).replace("## CURRENT TASK\n\nUser request: (empty)\n\n", "")
