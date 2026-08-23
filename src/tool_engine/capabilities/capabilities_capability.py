"""Capabilities meta-tools (describe deferred tools)."""

from __future__ import annotations

from typing import Any

from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.contracts.schema import tool_spec_to_json_schema
from src.tool_engine.models import ToolResult


class CapabilitiesCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {"capabilities.describe": self.describe}

    def describe(self, *, name: str) -> ToolResult:
        engine = getattr(self.services, "engine", None)
        if engine is None:
            return self.serializer.from_exception(
                "ToolEngine reference not configured",
                error_code="not_implemented",
            )
        try:
            spec = engine.registry.get(name)
        except Exception as exc:  # noqa: BLE001
            return self.serializer.from_exception(str(exc), error_code="tool_not_found")
        if not spec.deferred:
            schema = tool_spec_to_json_schema(spec)
            return self.serializer.serialize(
                {"name": name, "deferred": False, "schema": schema},
            )
        engine.expand_deferred_tool(name)
        schema = tool_spec_to_json_schema(spec)
        return self.serializer.serialize(
            {
                "name": name,
                "deferred": True,
                "expanded": True,
                "schema": schema,
            },
        )
