"""RNA wire-contract data models (see docs/02_api_spec.md)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Generic, Literal, TypeVar

T = TypeVar("T")

Confidence = Literal["heuristic", "precise", "whole_program"]


@dataclass(frozen=True, slots=True)
class RnaMeta:
    cost_ms: float
    cache_hit: bool
    truncated: bool
    confidence: Confidence | None = None
    degraded: bool = False
    reason: str | None = None
    error: str | None = None
    tokens_estimate: int = 0


@dataclass(frozen=True, slots=True)
class RnaResult(Generic[T]):
    data: T
    meta: RnaMeta

    def to_dict(self) -> dict[str, Any]:
        return {"data": _to_jsonable(self.data), "meta": asdict(self.meta)}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if hasattr(value, "__dataclass_fields__"):
        return {k: _to_jsonable(getattr(value, k)) for k in value.__dataclass_fields__}
    return value


@dataclass(frozen=True, slots=True)
class SymbolRef:
    name: str
    kind: Literal["function", "method", "class", "interface", "struct", "variable", "constant"]
    file: str
    line_start: int
    line_end: int
    signature: str | None = None
    docstring: str | None = None
    language: str = "python"


@dataclass(frozen=True, slots=True)
class FileSlice:
    path: str
    start_line: int
    end_line: int
    content: str
    total_lines: int
    truncated: bool


@dataclass(frozen=True, slots=True)
class ImportEdge:
    from_file: str
    to: str
    external: bool
    symbols: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ImportGraph:
    edges: tuple[ImportEdge, ...]
    scope: str | None


@dataclass(frozen=True, slots=True)
class CallEdge:
    caller: SymbolRef
    callee_name: str
    call_site_line: int


@dataclass(frozen=True, slots=True)
class TestLink:
    test_symbol: SymbolRef | None
    test_file: str
    target: str
    relation: Literal["direct_import", "naming_convention", "co_change"]
    confidence: float


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    symbol: SymbolRef
    depth: int
    call_site_line: int | None


@dataclass(frozen=True, slots=True)
class WorkflowTrace:
    entrypoint: str
    steps: tuple[WorkflowStep, ...]
    truncated_by_depth: bool


@dataclass(frozen=True, slots=True)
class HLDNode:
    id: str
    kind: Literal["package", "module", "external_dependency"]
    entrypoint: bool = False


@dataclass(frozen=True, slots=True)
class HLDEdge:
    from_id: str
    to_id: str
    weight: int


@dataclass(frozen=True, slots=True)
class HLDModel:
    nodes: tuple[HLDNode, ...]
    edges: tuple[HLDEdge, ...]
    mermaid: str | None = None


@dataclass(frozen=True, slots=True)
class LLDNode:
    symbol: SymbolRef
    node_kind: Literal["class", "function", "method"]


@dataclass(frozen=True, slots=True)
class LLDEdge:
    from_id: str
    to_id: str
    kind: Literal["calls", "inherits", "composes", "implements"]


@dataclass(frozen=True, slots=True)
class LLDModel:
    scope: str
    nodes: tuple[LLDNode, ...]
    edges: tuple[LLDEdge, ...]
    mermaid: str | None = None


@dataclass(frozen=True, slots=True)
class SearchHit:
    file: str
    line: int
    snippet: str
    match: str


@dataclass(frozen=True, slots=True)
class SemanticHit:
    file: str
    symbol: str | None
    start_line: int
    end_line: int
    snippet: str
    score: float


@dataclass(frozen=True, slots=True)
class WebResult:
    title: str
    url: str
    snippet: str
    source: str
    fetched_at: str


@dataclass(frozen=True, slots=True)
class WholeProgramGraph:
    """Internal Tier-3 normalized graph (not part of public wire contract)."""

    call_edges: tuple[CallEdge, ...] = ()
    inherit_edges: tuple[LLDEdge, ...] = ()
    import_edges: tuple[ImportEdge, ...] = ()
    symbols: tuple[SymbolRef, ...] = ()
