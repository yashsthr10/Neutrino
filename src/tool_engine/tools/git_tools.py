"""ToolSpec definitions for git.* tools."""

from __future__ import annotations

from src.config.constants import TOOL_AVAILABLE_STATES
from src.tool_engine.models import ToolParam, ToolSpec


def git_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="git.commit",
            description="Stage all changes and create a git commit.",
            category="git",
            handler_key="git.commit",
            states=TOOL_AVAILABLE_STATES,
            when_to_use="User asked to commit and changes are ready.",
            when_not_to_use="Do not invent commits; avoid force operations.",
            pairs_with=("git.diff", "executor.apply"),
            parameters=(ToolParam("message", "string", False, "Commit message"),),
        ),
        ToolSpec(
            name="git.undo",
            description="Undo the last commit with git reset --mixed HEAD~1.",
            category="git",
            handler_key="git.undo",
            states=TOOL_AVAILABLE_STATES,
            deferred=True,
            when_to_use="User asked to undo the last commit; keep it rare.",
            when_not_to_use="Destructive history rewrite beyond mixed reset.",
            pairs_with=("git.diff", "git.commit"),
            parameters=(),
        ),
        ToolSpec(
            name="git.diff",
            description="Show git working-tree or staged diff.",
            category="git",
            handler_key="git.diff",
            states=TOOL_AVAILABLE_STATES,
            when_to_use="Inspect uncommitted changes in the working tree.",
            when_not_to_use="Use executor.diff for the last apply-only change id.",
            pairs_with=("git.commit", "executor.diff"),
            parameters=(
                ToolParam("staged", "boolean", False, "Staged only", False),
                ToolParam("path", "string", False, "Optional path filter"),
            ),
        ),
    ]
