"""ToolSpec definitions for research.* tools."""

from __future__ import annotations

from src.config.constants import TOOL_AVAILABLE_STATES
from src.tool_engine.models import ToolParam, ToolSpec


def research_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="research.web",
            description="Search the web for external documentation or examples.",
            category="research",
            handler_key="research.web",
            states=TOOL_AVAILABLE_STATES,
            when_to_use="Need external docs/APIs not present in the repository.",
            when_not_to_use="Answers available via rna.* / context.resolve inside the repo.",
            pairs_with=("research.docs",),
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
            states=TOOL_AVAILABLE_STATES,
            when_to_use="Project documentation index when available.",
            when_not_to_use="Use rna.search / read_file for in-repo docs today.",
            pairs_with=("research.web", "rna.search"),
            parameters=(
                ToolParam("query", "string", True, "Docs query"),
                ToolParam("limit", "integer", False, "Max results", 5),
            ),
        ),
    ]
