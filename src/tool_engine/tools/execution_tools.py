"""ToolSpec definitions for executor.* tools."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

_STATES = frozenset({"EXECUTE"})
# Shell is available in VERIFY/REVIEW for repo-aware checks (still approval-gated).
_RUN_STATES = frozenset({"EXECUTE", "VERIFY", "REVIEW"})


def execution_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="executor.apply",
            description=(
                "Create or edit files. Preferred format=patch:\n"
                "*** Begin Patch\n"
                "*** Add File: path/to/file.py\n"
                "+line1\n+line2\n"
                "*** End Patch\n"
                "Or format=search_replace with <<<<<<< SEARCH / ======= / >>>>>>> REPLACE. "
                "Required to complete EXECUTE phase."
            ),
            category="execution",
            handler_key="executor.apply",
            states=_STATES,
            parameters=(
                ToolParam("patch", "string", True, "Patch / SEARCH-REPLACE / udiff payload"),
                ToolParam("path", "string", False, "Optional target path hint"),
                ToolParam(
                    "format",
                    "string",
                    False,
                    "Edit format: auto | patch | search_replace | udiff",
                    "patch",
                ),
                ToolParam("dry_run", "boolean", False, "Parse/match only; do not write", False),
            ),
        ),
        ToolSpec(
            name="executor.rollback",
            description="Rollback a prior executor.apply change by change_id.",
            category="execution",
            handler_key="executor.rollback",
            states=_STATES,
            parameters=(ToolParam("change_id", "string", False, "Change identifier"),),
        ),
        ToolSpec(
            name="executor.diff",
            description="Show unified diff for a prior apply (or last change).",
            category="execution",
            handler_key="executor.diff",
            states=_STATES,
            parameters=(
                ToolParam("path", "string", False, "Optional path filter"),
                ToolParam("change_id", "string", False, "Optional change id"),
            ),
        ),
        ToolSpec(
            name="executor.run",
            description=(
                "Run a shell command in the repo (e.g. ls, make test, npm test). "
                "Requires approved=true (host/TUI must confirm before setting this). "
                "Prefer verify.probe / rna.list_files for structure discovery."
            ),
            category="execution",
            handler_key="executor.run",
            states=_RUN_STATES,
            parameters=(
                ToolParam("command", "string", True, "Shell command"),
                ToolParam(
                    "approved",
                    "boolean",
                    False,
                    "Must be true after explicit user/host approval",
                    False,
                ),
                ToolParam("timeout_s", "number", False, "Timeout seconds", 120),
            ),
        ),
    ]
