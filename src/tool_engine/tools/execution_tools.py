"""ToolSpec definitions for executor.* tools."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

_STATES = frozenset(
    {"AGENT", "PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW"}
)


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
                "Or format=search_replace with <<<<<<< SEARCH / ======= / >>>>>>> REPLACE."
            ),
            category="execution",
            handler_key="executor.apply",
            states=_STATES,
            when_to_use="Implementing or fixing after you have read the target (or are creating a new file).",
            when_not_to_use="Before reading an existing file; not for running tests or shell.",
            pairs_with=("rna.read_file", "executor.diff", "tests.run"),
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
            when_to_use="Need to undo a prior apply in this run.",
            when_not_to_use="Prefer a new corrective apply when the fix is small.",
            pairs_with=("executor.apply", "executor.diff"),
            parameters=(ToolParam("change_id", "string", False, "Change identifier"),),
        ),
        ToolSpec(
            name="executor.diff",
            description="Show unified diff for a prior apply (or last change).",
            category="execution",
            handler_key="executor.diff",
            states=_STATES,
            when_to_use="Confirm what changed after an apply.",
            when_not_to_use="Use git.diff for full working-tree status vs last apply only.",
            pairs_with=("executor.apply", "git.diff"),
            parameters=(
                ToolParam("path", "string", False, "Optional path filter"),
                ToolParam("change_id", "string", False, "Optional change id"),
            ),
        ),
        ToolSpec(
            name="executor.run",
            description=(
                "Run a shell command in the repo (e.g. ls, make test, npm test). "
                "Requires approved=true (host/TUI must confirm before setting this)."
            ),
            category="execution",
            handler_key="executor.run",
            states=_STATES,
            when_to_use="Commands with no dedicated tool; project-specific scripts after approval.",
            when_not_to_use="Prefer rna.list_files / verify.probe / tests.run / lint.run when they apply.",
            pairs_with=("tests.run", "lint.run", "verify.probe"),
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
