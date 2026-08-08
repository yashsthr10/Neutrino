# RNA — API Specification

Contract-first: every data shape below is the **wire contract** — internal engine code may use richer types, but this is what crosses the RNA facade boundary (and what an MCP client sees, serialized to JSON).

## 1. Result envelope

Every `rna.*` call returns the same envelope, never a bare value:

```python
# rna/models.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeVar

T = TypeVar("T")

Confidence = Literal["heuristic", "precise", "whole_program"]

@dataclass(frozen=True, slots=True)
class RnaMeta:
    cost_ms: float
    cache_hit: bool
    truncated: bool
    confidence: Confidence | None = None   # None for methods with no language-tiering (get_file, search, ...)
    degraded: bool = False
    reason: str | None = None               # set when degraded=True or error is not None
    error: str | None = None                # "not_found" | "disabled" | None
    tokens_estimate: int = 0

@dataclass(frozen=True, slots=True)
class RnaResult(Generic[T]):
    data: T
    meta: RnaMeta
```

`error` is a field, not an exception, for every "the answer might legitimately be empty" case (symbol not found, no tests found, web search disabled, etc.). Exceptions (`RnaSecurityError`, `RnaConfigError`) are reserved for invariant violations per `01_architecture.md` §6.

---

## 2. Shared data models

```python
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
    to: str                 # resolved file path (internal) or module name (external)
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
    confidence: float   # 0.0-1.0 ranking signal, not the tier-level Confidence enum

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
    id: str                  # package/module path
    kind: Literal["package", "module", "external_dependency"]
    entrypoint: bool = False

@dataclass(frozen=True, slots=True)
class HLDEdge:
    from_id: str
    to_id: str
    weight: int               # number of underlying file-level import edges collapsed into this one

@dataclass(frozen=True, slots=True)
class HLDModel:
    nodes: tuple[HLDNode, ...]
    edges: tuple[HLDEdge, ...]
    mermaid: str | None = None   # only populated if format="mermaid" was requested

@dataclass(frozen=True, slots=True)
class LLDNode:
    symbol: SymbolRef
    node_kind: Literal["class", "function", "method"]

@dataclass(frozen=True, slots=True)
class LLDEdge:
    from_id: str            # "{file}:{symbol_name}"
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
    fetched_at: str    # ISO 8601
```

---

## 3. `get_symbol`

```python
def get_symbol(name: str, *, file_hint: str | None = None) -> RnaResult[list[SymbolRef]]
```

| | |
|---|---|
| Purpose | Resolve a symbol name to its definition site(s). |
| Params | `name` — exact or dotted symbol name (e.g. `Router.parse_request`). `file_hint` — narrows search to one file/module first (recommended whenever the caller already knows roughly where to look). |
| Returns | List (usually length 1; >1 means multiple definitions/overloads — caller should disambiguate using `file_hint`). |
| Backing | Graph Engine `symbol_index`; Tier 2 (LSP `workspace/symbol` + `textDocument/definition`) preferred, Tier 1 (tree-sitter def extraction) fallback. |
| Cost class | Cheap (cached after first repo-wide symbol index build per language). |
| `meta.error` | `"not_found"` if no match. |

---

## 4. `get_file`

```python
def get_file(path: str, *, start_line: int | None = None, end_line: int | None = None) -> RnaResult[FileSlice]
```

| | |
|---|---|
| Purpose | Read a file, optionally a bounded slice. |
| Params | `path` — repo-relative. `start_line`/`end_line` — 1-indexed, inclusive; omit both for the whole file (still capped, see below). |
| Returns | `FileSlice`. If no range is given and the file exceeds the default line cap (200 lines), the slice is truncated and `truncated=True` — callers that genuinely need more pass an explicit range or repeated calls, never get an unbounded read by accident. |
| Backing | Repo Analyzer. |
| Cost class | Cheap; no cache needed beyond the OS page cache — content hash is still recorded for other methods' cache keys. |
| `meta.error` | `"not_found"` if the path does not exist or resolves outside the repo root (in which case `RnaSecurityError` is raised instead — see `01_architecture.md` §6). |

---

## 5. `get_files_with_name`

```python
def get_files_with_name(pattern: str, *, limit: int = 50) -> RnaResult[list[str]]
```

| | |
|---|---|
| Purpose | Find file paths by name/glob without reading contents (e.g. `pattern="**/test_*.py"` or `pattern="router"` fuzzy). |
| Returns | Repo-relative paths, ranked by (exact basename match > prefix match > fuzzy match), then by path depth (shallower first). |
| Backing | Repo Analyzer tree (respecting standard ignore rules: `.git`, `node_modules`, build/venv dirs, `.gitignore`). |
| Cost class | Cheap; tree walk cached and invalidated on filesystem change (see `04_indexing_and_caching.md`). |

---

## 6. `get_import_graph`

```python
def get_import_graph(scope: str | None = None) -> RnaResult[ImportGraph]
```

| | |
|---|---|
| Purpose | File/module-level dependency edges: what imports what. |
| Params | `scope` — a file, directory, or package path to limit the graph to; `None` means repo-wide (still capped — see performance budgets in `04_indexing_and_caching.md`). |
| Backing | Graph Engine; Tier 1 (tree-sitter import statement extraction) is normally sufficient and preferred here for speed — Tier 2/3 add little precision for plain import edges. |
| Cost class | Moderate for repo-wide (first call); cheap thereafter (cached, incrementally updated per changed file). |

---

## 7. `get_callers`

```python
def get_callers(symbol: str, *, file_hint: str | None = None, limit: int = 25) -> RnaResult[list[CallEdge]]
```

| | |
|---|---|
| Purpose | Reverse call graph: every call site that invokes `symbol`. The single most important pre-refactor question — "if I change this signature, what breaks?" |
| Backing | Tier 2 LSP `callHierarchy/incomingCalls` when available (`confidence="precise"`); Tier 3 whole-program call graph (`pyan3`/`pycg`, `go/callgraph`, clangd call hierarchy) when the repo-wide graph is already cached from a prior `get_lld`/`get_hld` call (`confidence="whole_program"`); Tier 1 name-based text search fallback (`confidence="heuristic"` — may include false positives from shadowed names, always labeled as such). |
| Returns | Up to `limit` call edges, ranked by confidence tier then by proximity (same package first). `meta.truncated=True` if more exist. |
| Cost class | Moderate on first call per symbol per tier; cached. |

---

## 8. `get_tests`

```python
def get_tests(target: str) -> RnaResult[list[TestLink]]
```

| | |
|---|---|
| Purpose | "What tests cover this file/symbol?" before making a change. |
| Params | `target` — a file path or a symbol name. |
| Algorithm | (1) reverse-import scan: test files that import the target's module (`relation="direct_import"`, high confidence); (2) naming convention: `test_foo.py`/`foo_test.go`/`foo.test.ts`/`test_foo.cpp` paired with `foo.*` (`relation="naming_convention"`); (3) Git Analyzer co-change signal: files historically committed together with the target (`relation="co_change"`, lowest confidence, useful when 1 and 2 find nothing). Results are deduplicated and ranked by confidence, highest first. |
| Backing | Graph Engine `test_linker` + Git Analyzer `history`. |
| Cost class | Moderate first call (needs import graph + git log scan for the target's history); cached. |

---

## 9. `get_workflow`

```python
def get_workflow(entrypoint: str, *, max_depth: int = 4) -> RnaResult[WorkflowTrace]
```

| | |
|---|---|
| Purpose | "What happens when X runs?" — trace execution from an entry point (a CLI command handler, an HTTP route function, a `main()`) forward through the call graph. |
| Params | `entrypoint` — a symbol name or `file:line`. `max_depth` — bounded BFS depth (hard cap enforced server-side regardless of requested value; default max is 6). |
| Returns | `WorkflowTrace.steps` — a depth-ordered list of `WorkflowStep` (not a flat call list; depth is preserved so the caller can render an indented trace or a sequence diagram if it chooses to). `truncated_by_depth=True` if the walk was cut off before it naturally terminated. |
| Backing | Graph Engine `design_recovery`, built on the same call-graph primitives as `get_callers` but walking forward (outgoing calls) instead of backward. |
| Cost class | Moderate–expensive depending on fan-out; cycles are detected and broken (a node is not revisited within the same trace). |

---

## 10. `get_hld`

```python
def get_hld(*, scope: str | None = None, format: Literal["json", "mermaid"] = "json") -> RnaResult[HLDModel]
```

| | |
|---|---|
| Purpose | Bird's-eye architecture: package/module boundaries and the dependencies between them, plus detected entry points — a "read the README to understand the codebase" substitute that is derived from the actual code and always stays in sync with it. |
| Algorithm | (1) Repo Analyzer tree gives package/module boundaries (typically one HLD node per top-level source directory, configurable granularity). (2) `get_import_graph` at file level, collapsed ("aggregated") to package level: an edge `pkg_a -> pkg_b` with `weight=N` means N file-level import edges cross that boundary. (3) Entry-point detection heuristics per language (`if __name__ == "__main__"`, `func main()`, CLI command decorators, HTTP route decorators/annotations) mark `HLDNode.entrypoint=True`. |
| Params | `scope` — limit to a subtree (e.g. `"src/"` to exclude `tests/`, `docs/`). `format="mermaid"` additionally populates `HLDModel.mermaid` with a renderable diagram string for human display — the default `json` return stays machine-cheap for agent reasoning. |
| Backing | Graph Engine `design_recovery` + Repo Analyzer. **Deliberately does not call an LLM** — RNA supplies the structural facts only; prose narration of the architecture is left to whatever chat model the calling agent uses, keeping RNA's core fully deterministic. |
| Cost class | Expensive on first call for large repos (full graph aggregation); cached and incrementally invalidated (see `04_indexing_and_caching.md`). |

---

## 11. `get_lld`

```python
def get_lld(scope: str, *, format: Literal["json", "mermaid"] = "json") -> RnaResult[LLDModel]
```

| | |
|---|---|
| Purpose | Class/function-level structure for a specific file, module, or symbol: classes, their methods/attributes, inheritance, and the call/composition relationships between functions in scope. |
| Params | `scope` — a file or symbol path (required; unlike `get_hld`, LLD is never repo-wide by default — that would produce a huge, mostly irrelevant answer for no benefit). `format` as in `get_hld`. |
| Backing | Language Tier 3 tools specifically: **Python** → `pyan3` (call graph) + `pyreverse` (class/inheritance structure) merged into one `LLDModel`; **JavaScript/TypeScript** → `ts-morph` AST traversal for classes + `madge`/`dependency-cruiser` for in-scope call/require edges; **Go** → `go/packages` + `golang.org/x/tools/go/callgraph` for the in-scope call graph (Go has no classes; `LLDNode.node_kind` stays `"function"`); **C/C++** → `clangd` call hierarchy for functions + `universal-ctags`/header parsing for class/struct relationships. Full matrix in `03_language_adapters.md` §3. Falls back to a Tier 1/2-derived approximation (fewer edges, `meta.degraded=True`) if the Tier 3 tool for that language is not installed. |
| Cost class | Expensive on first call per scope (spawns an external analyzer); cached per `(scope, content hash, tool version)`. |

---

## 12. `search`

```python
def search(query: str, *, glob: str | None = None, limit: int = 50) -> RnaResult[list[SearchHit]]
```

| | |
|---|---|
| Purpose | Fast literal/regex search across the repo — the same job `ripgrep` does for Claude Code and most CLI agents today; the default "I don't know where this is, let me grep" tool. |
| Params | `query` — literal or regex (regex support is flagged explicitly, not auto-detected, to avoid surprising escaping bugs). `glob` — restrict to a path pattern (e.g. `"src/**/*.py"`). |
| Backing | Search Engine, backed by `ripgrep` (or a Python `re` fallback if `rg` is not on PATH — same tiered-degradation philosophy as language tools). |
| Cost class | Cheap; no cache needed (ripgrep is already fast; results are query-specific and repo state can change between calls). |

---

## 13. `semantic_search`

```python
def semantic_search(query: str, *, limit: int = 10) -> RnaResult[list[SemanticHit]]
```

| | |
|---|---|
| Purpose | "Find the code that does X" when you don't know the exact name/keyword — the same job Cursor's embedding index does. |
| Params | `query` — natural-language description. |
| Algorithm | Repo is chunked along **semantic boundaries** (function/class bodies, via Tier 1 tree-sitter node ranges — not fixed-size sliding windows, which cut mid-function and hurt retrieval quality), embedded with a configured embedding model, stored in a local vector store, and queried by cosine similarity. |
| Backing | Embedding Engine. |
| Cost class | Expensive on first repo index build (proportional to repo size — this is the one case where an optional background warm-up is worth offering, see `04_indexing_and_caching.md` §3); cheap per query thereafter; incrementally updated per changed file (re-embed only changed chunks). |

---

## 14. `google_search`

```python
def google_search(query: str, *, limit: int = 5) -> RnaResult[list[WebResult]]
```

| | |
|---|---|
| Purpose | External knowledge: library documentation, error message lookups, API references — anything not in the repository. |
| Backing | Web Engine, a pluggable provider (Google Custom Search API by default; Bing/SerpAPI/DuckDuckGo as alternates). |
| Guardrails | Requires `RnaConfig.web_search_enabled=True` (opt-in); every call is a logged network-egress event (see `05_tool_contract_and_safety.md` §4); results are cached by query hash with a TTL (default 24h) — not invalidated by repo state, since this answers questions about the outside world. |
| Cost class | Network-latency bound (hundreds of ms); rate-limited per provider quota. |
| `meta.error` | `"disabled"` if opted out — returned as data, not raised, so a calling agent can gracefully skip web-dependent steps. |

---

## 15. Errors

```python
class RnaError(Exception): ...
class RnaSecurityError(RnaError): ...   # path traversal, symlink escape, scope violation
class RnaConfigError(RnaError): ...     # invalid configuration detected at startup, not at call time
```

All other "nothing found" / "tool unavailable" cases are represented in `RnaMeta`, not exceptions — see `01_architecture.md` §6.
