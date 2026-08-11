"""Aggregator — flatten RnaResult payloads into RepositoryContextItem list."""

from __future__ import annotations


from src.context.runtime.repository_context import RepositoryContextItem
from src.rna.models import (
    CallEdge,
    FileSlice,
    ImportGraph,
    RnaResult,
    SearchHit,
    SemanticHit,
    SymbolRef,
    TestLink,
    WorkflowTrace,
)


def _tokens(text: str) -> int:
    return max(1, len(text.split())) if text else 0


class Aggregator:
    def aggregate(self, rna_results: list[tuple[str, RnaResult]]) -> list[RepositoryContextItem]:
        items: list[RepositoryContextItem] = []
        for method_name, result in rna_results:
            items.extend(self._flatten(method_name, result))
        return items

    def _flatten(self, method: str, result: RnaResult) -> list[RepositoryContextItem]:
        data = result.data
        if data is None:
            return []
        meta_tokens = result.meta.tokens_estimate

        if method == "get_file" and isinstance(data, FileSlice):
            return [
                RepositoryContextItem(
                    kind="file",
                    payload=data,
                    relevance=0.0,
                    tokens_estimate=meta_tokens or _tokens(data.content),
                    source_method=method,
                )
            ]

        if method == "get_files_with_name" and isinstance(data, list):
            return [
                RepositoryContextItem(
                    kind="file",
                    payload=path,
                    relevance=0.0,
                    tokens_estimate=1,
                    source_method=method,
                )
                for path in data
                if isinstance(path, str)
            ]

        if method == "get_symbol" and isinstance(data, list):
            return [
                RepositoryContextItem(
                    kind="symbol",
                    payload=s,
                    relevance=0.0,
                    tokens_estimate=meta_tokens or 8,
                    source_method=method,
                )
                for s in data
                if isinstance(s, SymbolRef)
            ]

        if method == "get_import_graph" and isinstance(data, ImportGraph):
            return [
                RepositoryContextItem(
                    kind="import_edge",
                    payload=e,
                    relevance=0.0,
                    tokens_estimate=4,
                    source_method=method,
                )
                for e in data.edges
            ]

        if method == "get_callers" and isinstance(data, list):
            return [
                RepositoryContextItem(
                    kind="call_edge",
                    payload=e,
                    relevance=0.0,
                    tokens_estimate=6,
                    source_method=method,
                )
                for e in data
                if isinstance(e, CallEdge)
            ]

        if method == "get_tests" and isinstance(data, list):
            return [
                RepositoryContextItem(
                    kind="test_link",
                    payload=t,
                    relevance=0.0,
                    tokens_estimate=4,
                    source_method=method,
                )
                for t in data
                if isinstance(t, TestLink)
            ]

        if method == "get_workflow" and isinstance(data, WorkflowTrace):
            return [
                RepositoryContextItem(
                    kind="workflow_step",
                    payload=step,
                    relevance=0.0,
                    tokens_estimate=6,
                    source_method=method,
                )
                for step in data.steps
            ]

        if method == "search" and isinstance(data, list):
            return [
                RepositoryContextItem(
                    kind="search_hit",
                    payload=h,
                    relevance=0.0,
                    tokens_estimate=_tokens(h.snippet) if isinstance(h, SearchHit) else 4,
                    source_method=method,
                )
                for h in data
            ]

        if method == "semantic_search" and isinstance(data, list):
            return [
                RepositoryContextItem(
                    kind="semantic_hit",
                    payload=h,
                    relevance=float(getattr(h, "score", 0.0)),
                    tokens_estimate=_tokens(getattr(h, "snippet", "") or ""),
                    source_method=method,
                )
                for h in data
                if isinstance(h, SemanticHit)
            ]

        # Fallback: wrap opaque payload
        return [
            RepositoryContextItem(
                kind="search_hit",
                payload=data,
                relevance=0.0,
                tokens_estimate=meta_tokens or 4,
                source_method=method,
            )
        ]
