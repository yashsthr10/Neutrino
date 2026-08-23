"""agent.task subagent tool spec."""

from __future__ import annotations

from src.config.constants import TOOL_AVAILABLE_STATES
from src.tool_engine.models import ToolParam, ToolSpec


def agent_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="agent.task",
            description=(
                "Run a bounded read-only sub-exploration (max 5 tool steps) and return a summary."
            ),
            category="agent",
            handler_key="agent.task",
            states=TOOL_AVAILABLE_STATES,
            when_to_use="Heavy repo exploration that would bloat the main thread context.",
            when_not_to_use="A single read/search tool suffices.",
            pairs_with=("context.resolve", "rna.get_hld"),
            parameters=(
                ToolParam("prompt", "string", True, "Exploration goal for the subagent"),
                ToolParam("scope", "string", False, "Optional repo-relative scope path"),
            ),
        ),
    ]
