"""ToolSpec definitions for research.* tools."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

_STATES = frozenset({"PLAN", "CONTEXT"})


def research_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="research.web",
            description="Search the web for external documentation or examples.",
            category="research",
            handler_key="research.web",
            states=_STATES,
            parameters=(
                ToolParam("query", "string", True, "Search query"),
                ToolParam("limit", "integer", False, "Max results", 5),
            ),
        ),
        ToolSpec(
            name="research.docs",
            description="Search project/docs index (not implemented in Phase A).",
            category="research",
            handler_key="research.docs",
            states=_STATES,
            parameters=(
                ToolParam("query", "string", True, "Docs query"),
                ToolParam("limit", "integer", False, "Max results", 5),
            ),
        ),
    ]
