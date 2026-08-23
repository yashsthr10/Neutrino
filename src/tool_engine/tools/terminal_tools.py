"""ToolSpec definitions for terminal.* tools."""

from __future__ import annotations

from src.config.constants import TERMINAL_DEFAULT_TIMEOUT_S, TOOL_AVAILABLE_STATES
from src.tool_engine.models import ToolParam, ToolSpec


def terminal_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="terminal.run",
            description=(
                "Run an arbitrary shell command in the repository with full terminal access. "
                "Supports repo-relative cwd, extra env vars, and stdin. "
                "Requires approved=true (host/TUI must confirm before setting this)."
            ),
            category="terminal",
            handler_key="terminal.run",
            states=TOOL_AVAILABLE_STATES,
            when_to_use=(
                "Any shell command: build, install, git ops, scripts, diagnostics, "
                "or project tooling without a dedicated tool."
            ),
            when_not_to_use=(
                "Creating/editing source files (use executor.apply); running tests/lint "
                "when tests.run / lint.run apply; listing files (use rna.list_files)."
            ),
            pairs_with=("tests.run", "lint.run", "verify.probe", "executor.apply"),
            parameters=(
                ToolParam("command", "string", True, "Shell command to execute"),
                ToolParam(
                    "cwd",
                    "string",
                    False,
                    "Optional repo-relative working directory",
                ),
                ToolParam(
                    "env",
                    "object",
                    False,
                    "Optional environment variables to merge into the process env",
                ),
                ToolParam(
                    "stdin",
                    "string",
                    False,
                    "Optional stdin text piped to the command",
                ),
                ToolParam(
                    "approved",
                    "boolean",
                    False,
                    "Must be true after explicit user/host approval",
                    False,
                ),
                ToolParam(
                    "timeout_s",
                    "number",
                    False,
                    "Timeout in seconds",
                    TERMINAL_DEFAULT_TIMEOUT_S,
                ),
            ),
        ),
    ]
