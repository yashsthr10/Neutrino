"""Conditional L2 section gates (Cursor Skills-style prompt injection)."""

from __future__ import annotations

import re
from typing import Any

_ARCH_KEYWORDS = re.compile(
    r"\b(architecture|architectural|diagram|hld|lld|module structure|"
    r"how does .+ fit|repo structure|subsystem|dependency map)\b",
    re.I,
)
_EDIT_KEYWORDS = re.compile(
    r"\b(implement|refactor|fix|add|update|change|modify|create|edit|patch|migrate)\b",
    re.I,
)
_SHELL_KEYWORDS = re.compile(
    r"\b(run|test|build|install|npm|pip|make|shell|terminal|command|execute)\b",
    re.I,
)

_EDIT_PHASES = frozenset({"IMPLEMENT", "REPAIR", "PLAN"})
_SHELL_PHASES = frozenset({"IMPLEMENT", "VERIFY", "REPAIR"})


def _tool_names(tools: list[Any] | tuple[Any, ...]) -> set[str]:
    names: set[str] = set()
    for t in tools:
        name = getattr(t, "name", None)
        if isinstance(name, str) and name:
            names.add(name)
    return names


def should_inject_architecture_diagrams(
    tools: list[Any] | tuple[Any, ...],
    *,
    query: str = "",
    task_complexity: str | None = None,
    tools_called: tuple[str, ...] | list[str] = (),
) -> bool:
    names = _tool_names(tools)
    if "rna.get_hld" not in names and "rna.get_lld" not in names:
        return False
    if (task_complexity or "").upper() == "COMPLEX":
        return True
    if _ARCH_KEYWORDS.search(query or ""):
        return True
    called = set(tools_called)
    return bool(called & {"rna.get_hld", "rna.get_lld"})


def should_inject_edit_formats(
    tools: list[Any] | tuple[Any, ...],
    *,
    query: str = "",
    agent_phase: str | None = None,
    tools_called: tuple[str, ...] | list[str] = (),
) -> bool:
    if "executor.apply" not in _tool_names(tools):
        return False
    phase = (agent_phase or "").upper()
    if phase in _EDIT_PHASES:
        return True
    if _EDIT_KEYWORDS.search(query or ""):
        return True
    return "executor.apply" in tools_called


def should_inject_terminal_preferences(
    tools: list[Any] | tuple[Any, ...],
    *,
    query: str = "",
    agent_phase: str | None = None,
) -> bool:
    if "terminal.run" not in _tool_names(tools):
        return False
    phase = (agent_phase or "").upper()
    if phase in _SHELL_PHASES:
        return True
    return bool(_SHELL_KEYWORDS.search(query or ""))


def should_inject_plan_tasks_guidance(
    *,
    task_complexity: str | None = None,
    tools: list[Any] | tuple[Any, ...] = (),
) -> bool:
    if "plan.set_tasks" not in _tool_names(tools):
        return False
    return (task_complexity or "").upper() == "COMPLEX"
