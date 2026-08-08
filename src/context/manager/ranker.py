"""Ranker — deterministic relevance scoring for repository items."""

from __future__ import annotations

from dataclasses import replace
from pathlib import PurePosixPath

from src.context.config import ContextConfig
from src.context.models import ContextRequest
from src.context.runtime.repository_context import RepositoryContextItem
from src.rna.models import CallEdge, FileSlice, SymbolRef, TestLink


_CONFIDENCE_WEIGHT = {
    "precise": 1.0,
    "whole_program": 0.9,
    "heuristic": 0.5,
}


class Ranker:
    def __init__(self, config: ContextConfig) -> None:
        self.config = config

    def rank(
        self, items: list[RepositoryContextItem], request: ContextRequest
    ) -> list[RepositoryContextItem]:
        scored = [replace(item, relevance=self._score(item, request)) for item in items]
        scored.sort(key=lambda i: i.relevance, reverse=True)
        return scored

    def _score(self, item: RepositoryContextItem, request: ContextRequest) -> float:
        cfg = self.config
        hint = self._hint_match(item, request)
        conf = self._confidence(item)
        recency = 0.5  # no git signal in v1; neutral
        relation = self._relation(item)
        distance = self._distance(item, request)
        return (
            cfg.w_hint * hint
            + cfg.w_confidence * conf
            + cfg.w_recency * recency
            + cfg.w_relation * relation
            - cfg.w_distance * distance
        )

    def _hint_match(self, item: RepositoryContextItem, request: ContextRequest) -> float:
        path = self._path_of(item)
        name = self._name_of(item)
        if path and path in request.file_hints:
            return 1.0
        if name and name in request.symbol_hints:
            return 1.0
        if path:
            for h in request.file_hints:
                if path.endswith(h) or h.endswith(path):
                    return 0.8
        return 0.0

    def _confidence(self, item: RepositoryContextItem) -> float:
        # Aggregator does not currently carry RNA confidence on items;
        # prefer precise source methods as a proxy.
        if item.source_method in ("get_symbol", "get_callers", "get_lld"):
            return 0.8
        if item.source_method in ("get_file", "get_tests"):
            return 0.7
        return 0.5

    def _relation(self, item: RepositoryContextItem) -> float:
        payload = item.payload
        if isinstance(payload, TestLink):
            return float(payload.confidence)
        if isinstance(payload, CallEdge):
            return 0.9
        return 0.5

    def _distance(self, item: RepositoryContextItem, request: ContextRequest) -> float:
        path = self._path_of(item)
        if not path or not request.file_hints:
            return 0.5
        hint_dirs = {str(PurePosixPath(h).parent) for h in request.file_hints}
        item_dir = str(PurePosixPath(path).parent)
        if item_dir in hint_dirs:
            return 0.0
        return 0.7

    def _path_of(self, item: RepositoryContextItem) -> str | None:
        p = item.payload
        if isinstance(p, str):
            return p
        if isinstance(p, FileSlice):
            return p.path
        if isinstance(p, SymbolRef):
            return p.file
        if isinstance(p, CallEdge):
            return p.caller.file
        if isinstance(p, TestLink):
            return p.test_file
        return getattr(p, "file", None) or getattr(p, "path", None)

    def _name_of(self, item: RepositoryContextItem) -> str | None:
        p = item.payload
        if isinstance(p, SymbolRef):
            return p.name
        if isinstance(p, CallEdge):
            return p.callee_name
        return getattr(p, "name", None) or getattr(p, "symbol", None)
