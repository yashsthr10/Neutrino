"""JSON schema emission for LLM tool bindings (incl. Gemini)."""

from __future__ import annotations

from src.tool_engine.contracts.schema import tool_spec_to_json_schema
from src.tool_engine.models import ToolParam, ToolSpec


def test_array_params_include_items() -> None:
    spec = ToolSpec(
        name="context.resolve",
        description="test",
        category="context",
        handler_key="context.resolve",
        states=frozenset({"PLAN"}),
        parameters=(
            ToolParam("task_description", "string", True, "goal"),
            ToolParam("file_hints", "array", False, "paths"),
            ToolParam("symbol_hints", "array", False, "symbols"),
            ToolParam("package", "object", False, "prior package"),
        ),
    )
    schema = tool_spec_to_json_schema(spec)
    props = schema["parameters"]["properties"]
    assert props["file_hints"]["type"] == "array"
    assert props["file_hints"]["items"] == {"type": "string"}
    assert props["symbol_hints"]["items"] == {"type": "string"}
    assert props["package"]["type"] == "object"
    assert props["package"]["additionalProperties"] is True


def test_plan_schemas_gemini_array_items(engine) -> None:
    for schema in engine.schemas_for_state("PLAN"):
        for name, prop in schema["parameters"]["properties"].items():
            if prop.get("type") == "array":
                assert "items" in prop, f"{schema['name']}.{name} missing items"


def test_array_param_with_object_items() -> None:
    spec = ToolSpec(
        name="plan.set_tasks",
        description="test",
        category="planning",
        handler_key="plan.set_tasks",
        states=frozenset({"PLAN"}),
        parameters=(ToolParam("tasks", "array", True, "checklist", item_type="object"),),
    )
    schema = tool_spec_to_json_schema(spec)
    prop = schema["parameters"]["properties"]["tasks"]
    assert prop["items"]["type"] == "object"
    assert prop["items"]["additionalProperties"] is True
