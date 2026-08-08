"""Research capabilities — web via RNA; docs stubbed."""

from __future__ import annotations

from typing import Any

from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.models import ToolResult


class ResearchCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {
            "research.web": self.web,
            "research.docs": self.docs,
        }

    def web(self, *, query: str, limit: int = 5) -> ToolResult:
        result = self.require_rna().google_search(query, limit=limit)
        return self.serializer.serialize(result)

    def docs(self, *, query: str, limit: int = 5) -> ToolResult:
        _ = query, limit
        return self.serializer.not_implemented("research.docs")
