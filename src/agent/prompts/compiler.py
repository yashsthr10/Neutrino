"""L1–L6 prompt compiler (Claude Code–style layered assembly)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.agent.prompts.layers.agent_state import render_agent_state
from src.agent.prompts.layers.capabilities import render_capabilities
from src.agent.prompts.layers.core import L1_CORE, L1_RESPONSE_CONTRACT
from src.agent.prompts.layers.environment import render_environment
from src.agent.prompts.layers.task_context import render_task_context
from src.agent.state_model import AgentState

DYNAMIC_BOUNDARY = "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__"


@dataclass(frozen=True, slots=True)
class PromptInputs:
    """Host-side inputs for one compiled system prompt."""

    user_query: str
    repo_path: str
    tools: list[Any] | tuple[Any, ...] = ()
    environment: dict[str, Any] | None = None
    agent_state: AgentState | None = None
    task_complexity: str | None = None
    code_changes: tuple[dict, ...] | list[dict] = ()
    plan_tasks: tuple[Any, ...] | list[Any] = ()
    repository_items: tuple[Any, ...] | list[Any] = ()
    checks_required: bool | None = None
    policy_reason: str | None = None
    harness: dict[str, Any] | None = None
    test_results: dict[str, Any] | None = None
    reminders: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class CompiledPrompt:
    system: str
    reminders: tuple[str, ...] = field(default_factory=tuple)


def compile_system_prompt(inputs: PromptInputs) -> CompiledPrompt:
    """Assemble L1+L2 (static-ish) + boundary + L3+L4+L5."""
    static = "\n".join(
        [
            L1_CORE.strip(),
            "",
            render_capabilities(list(inputs.tools)).strip(),
            "",
            L1_RESPONSE_CONTRACT.strip(),
        ]
    )
    dynamic = "\n".join(
        [
            render_environment(inputs.environment).strip(),
            "",
            render_task_context(
                user_query=inputs.user_query,
                task_complexity=inputs.task_complexity,
                repo_path=inputs.repo_path,
                code_changes=inputs.code_changes,
                plan_tasks=inputs.plan_tasks,
                repository_items=inputs.repository_items,
                checks_required=inputs.checks_required,
                policy_reason=inputs.policy_reason,
                harness=inputs.harness,
                test_results=inputs.test_results,
            ).strip(),
            "",
            render_agent_state(inputs.agent_state).strip(),
        ]
    )
    system = f"{static}\n\n{DYNAMIC_BOUNDARY}\n\n{dynamic}\n"
    return CompiledPrompt(system=system, reminders=inputs.reminders)


def format_reminders_message(reminders: tuple[str, ...] | list[str]) -> str | None:
    """L6 user-side injection body."""
    items = [r.strip() for r in reminders if isinstance(r, str) and r.strip()]
    if not items:
        return None
    blocks = [f"<system-reminder>\n{r}\n</system-reminder>" for r in items]
    return "\n\n".join(blocks)
