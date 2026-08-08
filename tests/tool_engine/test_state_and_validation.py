"""State gating, validation, and schema export tests."""

from __future__ import annotations

from src.tool_engine import ToolEngine, ToolRequest


def test_plan_schemas_include_context_and_rna(engine: ToolEngine) -> None:
    names = {s["name"] for s in engine.schemas_for_state("PLAN")}
    assert "context.resolve" in names
    assert "rna.find_symbol" in names
    assert "rna.read_file" in names
    assert "rna.search" in names
    assert "research.web" in names
    assert "executor.apply" not in names


def test_execute_schemas_include_executor_exclude_planner_only(engine: ToolEngine) -> None:
    names = {s["name"] for s in engine.schemas_for_state("EXECUTE")}
    assert "executor.apply" in names
    assert "executor.run" in names
    assert "context.refresh" in names
    assert "context.resolve" in names
    assert "rna.find_symbol" in names
    assert "rna.list_files" in names
    assert "context.expand" not in names


def test_verify_schemas_include_probe_shell_and_read(engine: ToolEngine) -> None:
    names = {s["name"] for s in engine.schemas_for_state("VERIFY")}
    assert "verify.probe" in names
    assert "tests.run" in names
    assert "lint.run" in names
    assert "executor.run" in names
    assert "rna.list_files" in names
    assert "rna.read_file" in names
    assert "executor.apply" not in names


def test_init_has_no_invokable_tools(engine: ToolEngine) -> None:
    assert engine.list_tools("INIT") == []


def test_permission_denied_for_wrong_state(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(name="context.expand", arguments={"task_description": "x"}),
        state="EXECUTE",
    )
    assert result.success is False
    assert result.meta.error == "permission_denied"


def test_validation_missing_required(engine: ToolEngine) -> None:
    result = engine.invoke(ToolRequest(name="rna.find_symbol", arguments={}), state="PLAN")
    assert result.success is False
    assert result.meta.error == "validation_error"


def test_unknown_tool(engine: ToolEngine) -> None:
    result = engine.invoke(ToolRequest(name="nope.tool", arguments={}), state="PLAN")
    assert result.success is False
    assert result.meta.error == "tool_not_found"
