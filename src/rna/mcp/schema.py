"""Generate JSON tool-call schemas from Rna method signatures."""

from __future__ import annotations

import inspect
from typing import Any, get_args, get_origin, get_type_hints

from src.rna.facade import Rna

_TOOLS = [
    "get_symbol",
    "get_file",
    "get_files_with_name",
    "get_import_graph",
    "get_callers",
    "get_tests",
    "get_workflow",
    "get_hld",
    "get_lld",
    "search",
    "semantic_search",
    "google_search",
]

_DESCRIPTIONS = {
    "get_symbol": "Resolve a symbol name to its definition site(s).",
    "get_file": "Read a file, optionally a bounded line slice.",
    "get_files_with_name": "Find file paths by name/glob without reading contents.",
    "get_import_graph": "File/module-level dependency edges: what imports what.",
    "get_callers": "Return every call site that invokes the given symbol (reverse call graph).",
    "get_tests": "Find tests covering a file or symbol.",
    "get_workflow": "Trace execution from an entry point through the call graph.",
    "get_hld": (
        "Bird's-eye package/module architecture model. "
        "Default format=json (token-efficient for agents); pass format=mermaid for diagrams. "
        "Use granularity=coarse|module|fine|file to control grouping depth."
    ),
    "get_lld": "Class/function-level structure for a scope.",
    "search": "Fast literal/regex search across the repository.",
    "semantic_search": "Find code by natural-language meaning.",
    "google_search": "External web search for docs/errors (opt-in).",
}


def _annotation_to_json_schema(ann: Any) -> dict[str, Any]:
    origin = get_origin(ann)
    if ann is int:
        return {"type": "integer"}
    if ann is bool:
        return {"type": "boolean"}
    if ann is float:
        return {"type": "number"}
    if ann is str or ann is None:
        return {"type": "string"}
    if origin is list:
        return {"type": "array"}
    args = get_args(ann)
    # Optional / Union
    if origin is type(None):
        return {"type": "string", "nullable": True}
    if (
        str(origin) in {"typing.Union", "types.UnionType"}
        or getattr(origin, "__name__", "") == "UnionType"
    ):
        non_none = [a for a in args if a is not type(None)]
        if len(non_none) == 1:
            schema = _annotation_to_json_schema(non_none[0])
            schema["nullable"] = True
            return schema
    if hasattr(ann, "__args__") and type(None) in get_args(ann):
        non_none = [a for a in get_args(ann) if a is not type(None)]
        if non_none:
            schema = _annotation_to_json_schema(non_none[0])
            schema["nullable"] = True
            return schema
    # Literal
    if get_origin(ann) is getattr(__import__("typing"), "Literal", None) or str(
        get_origin(ann)
    ).endswith("Literal"):
        return {"type": "string", "enum": list(get_args(ann))}
    return {"type": "string"}


def tool_schema(method_name: str) -> dict[str, Any]:
    method = getattr(Rna, method_name)
    hints = get_type_hints(method)
    sig = inspect.signature(method)
    properties: dict[str, Any] = {}
    required: list[str] = []
    for name, param in sig.parameters.items():
        if name == "self":
            continue
        ann = hints.get(name, str)
        schema = _annotation_to_json_schema(ann)
        schema["description"] = name
        if param.default is not inspect.Parameter.empty:
            if param.default is not None:
                schema["default"] = param.default
        else:
            required.append(name)
        properties[name] = schema
    return {
        "name": f"rna_{method_name}",
        "description": _DESCRIPTIONS.get(method_name, method_name),
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


def all_tool_schemas() -> list[dict[str, Any]]:
    return [tool_schema(name) for name in _TOOLS]


def dispatch(rna: Rna, tool_name: str, arguments: dict[str, Any]) -> Any:
    name = tool_name.removeprefix("rna_")
    if name not in _TOOLS:
        raise KeyError(f"unknown tool: {tool_name}")
    method = getattr(rna, name)
    result = method(**arguments)
    return result.to_dict()
