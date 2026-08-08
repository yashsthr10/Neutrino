"""Tool schema helpers between Tool Engine and providers."""

from __future__ import annotations

from typing import Any

from src.inference.models.request import ToolSpec


def tool_engine_schemas_to_specs(schemas: list[dict[str, Any]]) -> tuple[ToolSpec, ...]:
    out: list[ToolSpec] = []
    for s in schemas:
        params = s.get("parameters") if isinstance(s.get("parameters"), dict) else {}
        out.append(
            ToolSpec(
                name=str(s.get("name") or ""),
                description=str(s.get("description") or ""),
                parameters=params,
            )
        )
    return tuple(out)
