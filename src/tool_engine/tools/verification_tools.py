"""ToolSpec definitions for verification tools."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

_STATES = frozenset({"EXECUTE", "VERIFY", "REVIEW"})
_VERIFY_INSPECT = frozenset({"VERIFY", "REVIEW"})


def verification_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="verify.probe",
            description=(
                "Inspect the repo for test/lint harness markers and sample paths "
                "(structured alternative to ls -R). Use at the start of VERIFY."
            ),
            category="verification",
            handler_key="verify.probe",
            states=_VERIFY_INSPECT,
            parameters=(
                ToolParam(
                    "max_paths",
                    "integer",
                    False,
                    "Max sample paths to return",
                    80,
                ),
            ),
        ),
        ToolSpec(
            name="tests.run",
            description="Run the configured test command (default: pytest).",
            category="verification",
            handler_key="tests.run",
            states=_STATES,
            parameters=(ToolParam("target", "string", False, "Optional test target"),),
        ),
        ToolSpec(
            name="lint.run",
            description="Run the configured linter (default: ruff check).",
            category="verification",
            handler_key="lint.run",
            states=frozenset({"VERIFY", "REVIEW"}),
            parameters=(ToolParam("paths", "array", False, "Optional paths"),),
        ),
        ToolSpec(
            name="review.run",
            description="Run review checks (stub — not implemented).",
            category="verification",
            handler_key="review.run",
            states=frozenset({"VERIFY", "REVIEW"}),
            parameters=(ToolParam("summary", "string", False, "Optional review focus"),),
        ),
    ]
