"""RepositoryContext — bounded, ranked repository facts for one step."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

ItemKind = Literal[
    "file",
    "symbol",
    "import_edge",
    "call_edge",
    "test_link",
    "workflow_step",
    "search_hit",
    "semantic_hit",
]


@dataclass(frozen=True, slots=True)
class RepositoryContextItem:
    kind: ItemKind
    payload: Any
    relevance: float
    tokens_estimate: int
    source_method: str


@dataclass(frozen=True, slots=True)
class RepositoryContext:
    items: tuple[RepositoryContextItem, ...]
    tokens_estimate: int
    truncated: bool
    degraded: bool = False
    reason: str | None = None
