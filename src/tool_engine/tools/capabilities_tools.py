"""capabilities.describe meta-tool."""

from __future__ import annotations

from src.config.constants import TOOL_AVAILABLE_STATES
from src.tool_engine.models import ToolParam, ToolSpec


def capabilities_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="capabilities.describe",
            description="Load the full schema for a deferred tool by name.",
            category="capabilities",
            handler_key="capabilities.describe",
            states=TOOL_AVAILABLE_STATES,
            when_to_use="A deferred tool stub is present and you need its full parameters.",
            when_not_to_use="The tool is already fully described in the catalog.",
            pairs_with=(),
            parameters=(ToolParam("name", "string", True, "Tool name, e.g. research.docs"),),
        ),
    ]
