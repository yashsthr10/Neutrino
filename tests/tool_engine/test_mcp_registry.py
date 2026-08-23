"""MCP deferred tool registration."""

from __future__ import annotations

from src.tool_engine import RuntimeServices, build_tool_engine
from src.tool_engine.mcp_registry import mcp_tools_to_deferred_specs, register_mcp_deferred_tools


def test_mcp_deferred_specs_sorted_and_flagged() -> None:
    specs = mcp_tools_to_deferred_specs(["z.tool", "a.tool"])
    assert [s.name for s in specs] == ["a.tool", "z.tool"]
    assert all(s.deferred for s in specs)


def test_register_mcp_deferred_tools_appends_stubs() -> None:
    services = RuntimeServices()
    engine = build_tool_engine(services)
    before = {s.name for s in engine.list_tools("AGENT")}
    register_mcp_deferred_tools(engine, ["mcp.alpha", "mcp.beta"])
    after = engine.list_tools("AGENT")
    assert "mcp.alpha" in {s.name for s in after} - before
    stub = next(s for s in after if s.name == "mcp.alpha")
    assert stub.deferred is True
