"""ToolSpec definitions for verification tools."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

_STATES = frozenset(
    {"AGENT", "PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW"}
)


def verification_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="verify.probe",
            description=(
                "Inspect the repo for test/lint harness markers and sample paths "
                "(structured alternative to ls -R)."
            ),
            category="verification",
            handler_key="verify.probe",
            states=_STATES,
            when_to_use="Learn whether tests/lint exist and what to run after code changes.",
            when_not_to_use="You already know the harness from ENVIRONMENT / prior probe.",
            pairs_with=("tests.run", "lint.run"),
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
            when_to_use="Behavior changed or user asked for proof and a test harness exists.",
            when_not_to_use="Pure Q&A with no edits; waived when checks are not required.",
            pairs_with=("verify.probe", "executor.apply", "rna.find_tests"),
            parameters=(ToolParam("target", "string", False, "Optional test target"),),
        ),
        ToolSpec(
            name="lint.run",
            description="Run the configured linter (default: ruff check).",
            category="verification",
            handler_key="lint.run",
            states=_STATES,
            when_to_use="Lint harness is present and you need static checks (or tests are absent).",
            when_not_to_use="No lint harness; prefer tests.run when tests exist for behavior changes.",
            pairs_with=("verify.probe", "tests.run"),
            parameters=(ToolParam("paths", "array", False, "Optional paths"),),
        ),
        ToolSpec(
            name="review.run",
            description="Run review checks (stub — not implemented).",
            category="verification",
            handler_key="review.run",
            states=_STATES,
            when_to_use="Explicit review request when implemented.",
            when_not_to_use="Prefer tests.run / lint.run for verification today.",
            pairs_with=("tests.run", "lint.run"),
            parameters=(ToolParam("summary", "string", False, "Optional review focus"),),
        ),
    ]
