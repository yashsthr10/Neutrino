"""ToolSpec definitions for git.* tools."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

_STATES = frozenset({"EXECUTE"})


def git_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="git.commit",
            description="Stage all changes and create a git commit.",
            category="git",
            handler_key="git.commit",
            states=_STATES,
            parameters=(ToolParam("message", "string", False, "Commit message"),),
        ),
        ToolSpec(
            name="git.undo",
            description="Undo the last commit with git reset --mixed HEAD~1.",
            category="git",
            handler_key="git.undo",
            states=_STATES,
            parameters=(),
        ),
        ToolSpec(
            name="git.diff",
            description="Show git working-tree or staged diff.",
            category="git",
            handler_key="git.diff",
            states=_STATES,
            parameters=(
                ToolParam("staged", "boolean", False, "Staged only", False),
                ToolParam("path", "string", False, "Optional path filter"),
            ),
        ),
    ]
