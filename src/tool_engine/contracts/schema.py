"""JSON-schema helpers from ToolSpec parameters."""

from __future__ import annotations

from typing import Any

from src.tool_engine.models import ToolSpec


def tool_spec_to_json_schema(spec: ToolSpec) -> dict[str, Any]:
    """OpenAI/Anthropic/Gemini-style function schema for one tool.

    Gemini requires array properties to declare ``items``; bare
    ``{"type": "array"}`` is rejected with INVALID_ARGUMENT.
    """
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in spec.parameters:
        prop: dict[str, Any] = {"type": p.type, "description": p.description}
        if p.type == "array":
            if p.item_type == "object":
                prop["items"] = {"type": "object", "properties": {}, "additionalProperties": True}
            else:
                prop["items"] = {"type": p.item_type}
        elif p.type == "object":
            # Gemini also rejects empty object schemas without structure.
            prop["properties"] = {}
            prop["additionalProperties"] = True
        if p.default is not None:
            prop["default"] = p.default
        properties[p.name] = prop
        if p.required:
            required.append(p.name)
    return {
        "name": spec.name,
        "description": spec.description,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def specs_to_schemas(specs: list[ToolSpec]) -> list[dict[str, Any]]:
    return [tool_spec_to_json_schema(s) for s in specs]
