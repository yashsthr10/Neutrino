"""JSON-schema helpers from ToolSpec parameters."""

from __future__ import annotations

from typing import Any

from src.tool_engine.models import ToolSpec


def enrich_tool_description(spec: ToolSpec) -> str:
    """Merge when_to_use metadata into the provider-facing description."""
    parts = [spec.description.strip()]
    if spec.when_to_use.strip():
        parts.append(f"When to use: {spec.when_to_use.strip()}")
    if spec.when_not_to_use.strip():
        parts.append(f"When not to use: {spec.when_not_to_use.strip()}")
    if spec.pairs_with:
        parts.append("Pairs with: " + ", ".join(spec.pairs_with))
    return "\n".join(parts)


def tool_spec_to_json_schema(spec: ToolSpec, *, stub: bool = False) -> dict[str, Any]:
    """OpenAI/Anthropic/Gemini-style function schema for one tool."""
    if stub:
        return {
            "name": spec.name,
            "description": (
                f"{spec.description.strip()} "
                "(Deferred — call capabilities.describe with this name for full schema.)"
            ),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        }
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
        "description": enrich_tool_description(spec),
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


def specs_to_schemas(
    specs: list[ToolSpec],
    *,
    expanded_deferred: frozenset[str] | set[str] = frozenset(),
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for spec in specs:
        stub = spec.deferred and spec.name not in expanded_deferred
        out.append(tool_spec_to_json_schema(spec, stub=stub))
    return out
