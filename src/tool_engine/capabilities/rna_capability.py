"""RNA capabilities — intention tools mapped to RnaPort methods."""

from __future__ import annotations

from typing import Any

from src.rna.models import RnaMeta, RnaResult
from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.models import ToolResult


class RnaCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {
            "rna.find_symbol": self.find_symbol,
            "rna.trace_workflow": self.trace_workflow,
            "rna.find_tests": self.find_tests,
            "rna.find_related": self.find_related,
            "rna.semantic_search": self.semantic_search,
            "rna.read_file": self.read_file,
            "rna.search": self.search,
            "rna.list_files": self.list_files,
        }

    def find_symbol(self, *, name: str, file_hint: str | None = None) -> ToolResult:
        result = self.require_rna().get_symbol(name, file_hint=file_hint)
        return self.serializer.serialize(result)

    def trace_workflow(self, *, entrypoint: str, max_depth: int = 4) -> ToolResult:
        result = self.require_rna().get_workflow(entrypoint, max_depth=max_depth)
        return self.serializer.serialize(result)

    def find_tests(self, *, target: str) -> ToolResult:
        result = self.require_rna().get_tests(target)
        return self.serializer.serialize(result)

    def semantic_search(self, *, query: str, limit: int = 10) -> ToolResult:
        result = self.require_rna().semantic_search(query, limit=limit)
        return self.serializer.serialize(result)

    def read_file(
        self,
        *,
        path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> ToolResult:
        result = self.require_rna().get_file(path, start_line=start_line, end_line=end_line)
        return self.serializer.serialize(result)

    def search(
        self,
        *,
        query: str,
        glob: str | None = None,
        limit: int = 50,
    ) -> ToolResult:
        result = self.require_rna().search(query, glob=glob, limit=limit)
        return self.serializer.serialize(result)

    def list_files(self, *, pattern: str, limit: int = 50) -> ToolResult:
        result = self.require_rna().get_files_with_name(pattern, limit=limit)
        return self.serializer.serialize(result)

    def find_related(
        self,
        *,
        symbol: str,
        file_hint: str | None = None,
        limit: int = 25,
    ) -> ToolResult:
        """Compose callers + tests + import graph (no dedicated RNA method)."""
        rna = self.require_rna()
        callers = rna.get_callers(symbol, file_hint=file_hint, limit=limit)
        tests = rna.get_tests(symbol)
        imports = rna.get_import_graph(scope=file_hint)
        composed = RnaResult(
            data={
                "symbol": symbol,
                "callers": callers.to_dict(),
                "tests": tests.to_dict(),
                "imports": imports.to_dict(),
            },
            meta=RnaMeta(
                cost_ms=callers.meta.cost_ms + tests.meta.cost_ms + imports.meta.cost_ms,
                cache_hit=callers.meta.cache_hit
                and tests.meta.cache_hit
                and imports.meta.cache_hit,
                truncated=callers.meta.truncated or tests.meta.truncated or imports.meta.truncated,
                degraded=callers.meta.degraded or tests.meta.degraded or imports.meta.degraded,
                reason=callers.meta.reason or tests.meta.reason or imports.meta.reason,
            ),
        )
        return self.serializer.serialize(composed)
