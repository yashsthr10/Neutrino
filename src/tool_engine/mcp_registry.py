"""Register MCP tools as deferred ToolEngine stubs."""

from __future__ import annotations

from src.tool_engine.engine import ToolEngine
from src.tool_engine.models import ToolParam, ToolSpec


def mcp_tools_to_deferred_specs(tool_names: list[str]) -> list[ToolSpec]:
    """Convert MCP tool names to deferred ToolSpecs (stable sort by name)."""
    specs: list[ToolSpec] = []
    for name in sorted(tool_names):
        specs.append(
            ToolSpec(
                name=name,
                description=f"MCP tool `{name}` (deferred — use capabilities.describe).",
                category="mcp",
                handler_key=name,
                states=frozenset({"AGENT", "PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW"}),
                deferred=True,
                parameters=(ToolParam("arguments", "object", False, "Tool arguments"),),
            )
        )
    return specs


def register_mcp_deferred_tools(engine: ToolEngine, tool_names: list[str]) -> None:
    engine.register_deferred_tools(mcp_tools_to_deferred_specs(tool_names))
