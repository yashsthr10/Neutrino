"""State gating, validation, and schema export tests."""

from __future__ import annotations

from src.tool_engine import ToolEngine, ToolRequest
from src.tool_engine.contracts.schema import enrich_tool_description
from src.tool_engine.tools import all_tool_specs


def test_agent_schemas_include_full_surface(engine: ToolEngine) -> None:
    names = {s["name"] for s in engine.schemas_for_state("AGENT")}
    assert "context.resolve" in names
    assert "context.expand" in names
    assert "rna.find_symbol" in names
    assert "rna.read_file" in names
    assert "research.web" in names
    assert "executor.apply" in names
    assert "executor.run" in names
    assert "verify.probe" in names
    assert "tests.run" in names
    assert "lint.run" in names
    assert "git.diff" in names
    assert "plan.set_tasks" in names


def test_legacy_aliases_match_agent(engine: ToolEngine) -> None:
    agent = {s["name"] for s in engine.schemas_for_state("AGENT")}
    assert {s["name"] for s in engine.schemas_for_state("PLAN")} == agent
    assert {s["name"] for s in engine.schemas_for_state("EXECUTE")} == agent
    assert {s["name"] for s in engine.schemas_for_state("VERIFY")} == agent


def test_init_has_no_invokable_tools(engine: ToolEngine) -> None:
    assert engine.list_tools("INIT") == []


def test_schema_description_includes_when_to_use(engine: ToolEngine) -> None:
    schemas = {s["name"]: s for s in engine.schemas_for_state("AGENT")}
    desc = schemas["rna.semantic_search"]["description"]
    assert "When to use:" in desc


def test_enrich_tool_description_unit() -> None:
    spec = next(s for s in all_tool_specs() if s.name == "executor.apply")
    text = enrich_tool_description(spec)
    assert "When to use:" in text
    assert spec.when_to_use in text


def test_validation_missing_required(engine: ToolEngine) -> None:
    result = engine.invoke(ToolRequest(name="rna.find_symbol", arguments={}), state="AGENT")
    assert result.success is False
    assert result.meta.error == "validation_error"


def test_unknown_tool(engine: ToolEngine) -> None:
    result = engine.invoke(ToolRequest(name="nope.tool", arguments={}), state="AGENT")
    assert result.success is False
    assert result.meta.error == "tool_not_found"


def test_expand_allowed_in_agent(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(name="context.expand", arguments={"task_description": "x"}),
        state="AGENT",
    )
    # May succeed or fail on missing context backend wiring, but not permission_denied.
    assert result.meta.error != "permission_denied"
