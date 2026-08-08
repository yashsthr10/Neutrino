"""get_callers / callees with tiered providers + whole-program reuse."""

from __future__ import annotations

from src.rna.adapters.registry import LanguageRegistry
from src.rna.cache.keys import make_cache_key
from src.rna.cache.store import CacheStore
from src.rna.models import CallEdge, Confidence, WholeProgramGraph
from src.rna.repo_analyzer.fingerprint import content_hash, repo_fingerprint


class CallGraphService:
    def __init__(
        self,
        registry: LanguageRegistry,
        cache: CacheStore | None = None,
    ) -> None:
        self.registry = registry
        self.cache = cache
        self._wp_graphs: dict[str, WholeProgramGraph] = {}

    def remember_whole_program(self, scope: str, graph: WholeProgramGraph) -> None:
        self._wp_graphs[scope] = graph

    def get_callers(
        self,
        symbol: str,
        *,
        file_hint: str | None = None,
        limit: int = 25,
    ) -> tuple[list[CallEdge], Confidence, bool, str | None]:
        language = None
        if file_hint:
            language = self.registry.language_for_path(file_hint)
        if language is None:
            language = self.registry.primary_language()

        # Reuse cached whole-program graph if present
        for scope, graph in self._wp_graphs.items():
            if file_hint and not (file_hint == scope or file_hint.startswith(scope.rstrip("/") + "/")):
                continue
            short = symbol.split(".")[-1]
            edges = [
                e
                for e in graph.call_edges
                if e.callee_name == symbol or e.callee_name == short or e.callee_name.endswith("." + short)
            ]
            if edges:
                truncated = len(edges) > limit
                return edges[:limit], "whole_program", truncated, None

        providers = self.registry.resolve(language)
        reason: str | None = None
        best: list[CallEdge] = []
        confidence: Confidence = "heuristic"
        for provider in providers:
            if provider.tier == "whole_program":
                # Prefer point-query via LSP/structural; Tier3 used for bulk
                try:
                    wp = provider.build_whole_program_graph(file_hint or ".")
                except Exception as exc:  # noqa: BLE001
                    reason = f"tier3 failed: {exc}"
                    continue
                if wp is not None:
                    self.remember_whole_program(file_hint or ".", wp)
                    short = symbol.split(".")[-1]
                    edges = [
                        e
                        for e in wp.call_edges
                        if e.callee_name == symbol
                        or e.callee_name == short
                        or e.callee_name.endswith("." + short)
                    ]
                    if edges:
                        truncated = len(edges) > limit
                        return edges[:limit], "whole_program", truncated, reason
                continue
            try:
                found = provider.find_callers(symbol, file_hint)
            except Exception as exc:  # noqa: BLE001
                reason = f"{provider.tier} failed: {exc}"
                continue
            if found:
                best = found
                confidence = "precise" if provider.tier == "semantic" else "heuristic"
                break
        truncated = len(best) > limit
        return best[:limit], confidence, truncated, reason

    def get_callees(
        self,
        symbol: str,
        *,
        file_hint: str | None = None,
        limit: int = 50,
    ) -> tuple[list[CallEdge], Confidence]:
        language = None
        if file_hint:
            language = self.registry.language_for_path(file_hint)
        if language is None:
            language = self.registry.primary_language()
        for provider in self.registry.resolve(language):
            try:
                found = provider.find_callees(symbol, file_hint)
            except Exception:  # noqa: BLE001
                continue
            if found:
                conf: Confidence = "precise" if provider.tier == "semantic" else "heuristic"
                return found[:limit], conf
        return [], "heuristic"
