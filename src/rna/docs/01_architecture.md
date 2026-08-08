# RNA — Architecture

## 1. How RNA is embedded

RNA has exactly one core implementation and two thin surfaces on top of it:

```text
                     +-----------------------------+
                     |         Rna (facade)         |
                     |  Repo Analyzer | Graph Engine |
                     |  Embedding Eng | Search Engine|
                     |  Git Analyzer  | Web Engine   |
                     +---------------+---------------+
                                     |
              +----------------------+----------------------+
              |                                             |
   In-process Python import                        MCP server process
   (from rna import Rna)                            (rna serve --repo .)
              |                                             |
     Custom agent loop / tool layer            Any MCP-compatible client
     of the host application                    (Claude Code, Cursor, etc.)
```

Both surfaces call the exact same facade methods and return the exact same data contracts (`02_api_spec.md`); the MCP server (`05_tool_contract_and_safety.md` §2) is a thin JSON-RPC adapter with no independent logic, so behavior never diverges between "used as a library" and "used as an external tool."

---

## 2. Facade shape

```python
# src/rna/__init__.py
from __future__ import annotations

from typing import Protocol

class RnaPort(Protocol):
    """Read-only knowledge API over a repository. No side effects, no LLM calls."""

    def get_symbol(self, name: str, *, file_hint: str | None = None) -> RnaResult[list[SymbolRef]]: ...
    def get_file(self, path: str, *, start_line: int | None = None, end_line: int | None = None) -> RnaResult[FileSlice]: ...
    def get_files_with_name(self, pattern: str, *, limit: int = 50) -> RnaResult[list[str]]: ...
    def get_import_graph(self, scope: str | None = None) -> RnaResult[ImportGraph]: ...
    def get_callers(self, symbol: str, *, file_hint: str | None = None, limit: int = 25) -> RnaResult[list[CallEdge]]: ...
    def get_tests(self, target: str) -> RnaResult[list[TestLink]]: ...
    def get_workflow(self, entrypoint: str, *, max_depth: int = 4) -> RnaResult[WorkflowTrace]: ...
    def get_hld(self, *, scope: str | None = None) -> RnaResult[HLDModel]: ...
    def get_lld(self, scope: str, *, format: str = "json") -> RnaResult[LLDModel]: ...
    def search(self, query: str, *, glob: str | None = None, limit: int = 50) -> RnaResult[list[SearchHit]]: ...
    def semantic_search(self, query: str, *, limit: int = 10) -> RnaResult[list[SemanticHit]]: ...
    def google_search(self, query: str, *, limit: int = 5) -> RnaResult[list[WebResult]]: ...
```

`RnaPort` is a `Protocol` so the concrete `Rna` implementation, a scripted `FakeRna` (for tests / host-application development, no subprocesses, no I/O), and any future alternate backend all satisfy the same static type. Every method returns an `RnaResult[T]` envelope (`02_api_spec.md` §1) — never a bare value — so cost, cache, and confidence metadata always travel with the answer.

---

## 3. The three-tier language intelligence model

Different languages have different native tooling, and no single tool covers every language or every query shape. RNA resolves this with three tiers per language, tried in order, each an *upgrade* in precision over the previous one, never a hard requirement:

```text
Tier 1 -- Structural (tree-sitter)          always available, zero external process
   |  parses source into a concrete syntax tree
   |  extracts: symbol definitions, import/require statements, rough call sites (by name match)
   v
Tier 2 -- Semantic (Language Server Protocol)   opportunistic, needs a language server on PATH
   |  textDocument/definition, textDocument/references,
   |  callHierarchy/incomingCalls & outgoingCalls, workspace/symbol
   |  precise, type-aware, handles overloads/imports correctly
   v
Tier 3 -- Whole-program (per-language static analyzers)   opportunistic, needs a tool on PATH
   |  builds a whole-repo graph/diagram in one pass (call graph, class diagram, include graph)
   |  used specifically for get_hld / get_lld / bulk get_import_graph / bulk get_callers
   v
Result carries confidence: "heuristic" (Tier 1 only) | "precise" (Tier 2) | "whole_program" (Tier 3)
```

A single `LanguageProvider` protocol (see `03_language_adapters.md` §1) is implemented once per tier per language. The **registry** (`rna/adapters/registry.py`) probes tool availability once per process (`which gopls`, `which pyan3`, …), caches the probe result, and builds a provider chain per language. If Tier 2/3 tools are missing, RNA silently falls back to Tier 1 — it never raises `ToolNotFoundError` to the caller. This is what makes RNA usable in a bare-bones CI container and progressively better on a developer machine with language servers installed.

**Why this design, and not one bespoke tool per language chosen ad hoc:** an LSP client is a single piece of code that talks to `gopls`, `clangd`, `pyright`/`pylsp`, and `typescript-language-server` alike — Tier 2 is one adapter, many backends, for free precision on `get_symbol`/`get_callers`. Tree-sitter is one dependency covering roughly 40 grammars — Tier 1 is one adapter covering every language RNA might see, including ones nobody has written a Tier-3 tool for yet. Only Tier 3 (whole-repo diagram/graph export, which LSP does not do well) needs genuinely per-language tools, and that's exactly where `pyan`/`pyreverse` (Python), `madge`/`ts-morph` (JS/TS), `go/callgraph` (Go), and `clangd` call-hierarchy + `cscope` (C/C++) come in — see `03_language_adapters.md` for the full matrix.

---

## 4. Package layout

```text
rna/
  __init__.py              # RnaPort protocol, Rna facade export
  facade.py                 # Rna: composes the six engines, builds RnaResult envelopes
  models.py                  # SymbolRef, FileSlice, ImportGraph, CallEdge, TestLink,
                              # WorkflowTrace, HLDModel, LLDModel, SearchHit, SemanticHit,
                              # WebResult, RnaResult (see 02_api_spec.md)
  config.py                   # RnaConfig: limits, enabled tiers, cache dir, web opt-in
  cli.py                        # `rna serve`, `rna get-symbol ...` — CLI entry point

  repo_analyzer/
    tree.py                    # directory scan, ignore rules (.git, node_modules, ...)
    files.py                    # get_file, get_files_with_name
    fingerprint.py               # repo/file content hashing for cache keys

  graph_engine/
    symbol_index.py               # get_symbol (delegates to adapters/registry)
    import_graph.py                # get_import_graph
    call_graph.py                   # get_callers, BFS/DFS used by get_workflow
    design_recovery.py               # get_hld, get_lld, get_workflow orchestration
    test_linker.py                    # get_tests (imports + Git Analyzer co-change)

  search_engine/
    lexical.py                         # search() (ripgrep-backed)

  embedding_engine/
    chunker.py                          # semantic chunking on tree-sitter node boundaries
    vector_store.py                      # local vector store backend
    semantic_search.py                    # semantic_search()

  git_analyzer/
    history.py                             # blame, recent changes, co-change ranking

  web_engine/
    providers.py                            # pluggable web search providers
    web_search.py                            # google_search()

  adapters/                                  # the three-tier language intelligence model
    base.py                                   # LanguageProvider protocol
    tree_sitter_provider.py                    # Tier 1
    lsp_provider.py                             # Tier 2 (generic LSP client)
    python_tools.py                              # Tier 3: pyan3 / pyreverse / pycg wrappers
    js_ts_tools.py                                # Tier 3: madge / dependency-cruiser / ts-morph
    go_tools.py                                    # Tier 3: go/callgraph, gopls callgraph
    cpp_tools.py                                    # Tier 3: clangd call hierarchy, cscope/ctags
    registry.py                                      # language -> provider chain resolution

  cache/
    store.py                                          # on-disk cache + in-memory LRU
    invalidation.py                                     # content-hash / git-diff based invalidation

  mcp/
    server.py                                            # MCP server exposing every rna.* method
    schema.py                                             # rna.* -> JSON tool-call schema generation

  fake.py                                                 # FakeRna: scripted, no subprocess, for tests

  docs/                                                    # this design set
    README.md
    01_architecture.md
    02_api_spec.md
    03_language_adapters.md
    04_indexing_and_caching.md
    05_tool_contract_and_safety.md

  tests/
```

Small, focused modules; one clear owner per file; a `Protocol`-based port with a `fake.py` sibling for the facade — so RNA can be unit-tested and integrated into a host agent without ever spawning a subprocess.

---

## 5. Request lifecycle (example: `rna.get_callers("parse_request", file_hint="api/router.py")`)

```text
1. Caller (agent, before renaming/changing a signature) calls rna.get_callers(...)
2. Rna.facade routes to graph_engine.call_graph.get_callers()
3. call_graph resolves language from file_hint's extension -> "python"
4. adapters.registry returns provider chain for python: [LSP(pylsp/pyright) if on PATH, tree_sitter]
     (Tier 3 whole-program tools are preferred for *bulk* graph exports, not single-symbol lookups
      -- see 03_language_adapters.md S4 for when Tier 3 beats repeated Tier 2 calls)
5. cache.store checked with key = (repo_fingerprint, file content sha, "get_callers", symbol, tool_version)
     - HIT -> return cached CallEdge list immediately (no subprocess spawned)
     - MISS -> continue
6. Try Tier 2: spawn/reuse LSP server for python, request callHierarchy/incomingCalls
     - success -> confidence="precise"
     - server unavailable / times out -> fall to Tier 1
7. Tier 1 fallback: tree-sitter parse of files containing the symbol name (from a Tier-1-built
     symbol index), text-match call sites -> confidence="heuristic"
8. Result capped to `limit` (default 25), wrapped in RnaResult with meta.cost_ms, meta.cache_hit,
     meta.truncated, meta.confidence
9. cache.store writes the result keyed as in step 5
10. Returned to the caller (in-process return value, or serialized as an MCP tool-call response)
```

Subprocess- and I/O-bound tiers (LSP, Tier 3 tools) run through a bounded worker pool with a per-call timeout (see `04_indexing_and_caching.md` §4 performance budgets); a timeout degrades to the next tier rather than failing the call.

---

## 6. Degradation policy

RNA follows one rule everywhere: **never throw because a nice-to-have tool is missing; only throw because a required invariant was violated.**

| Situation | Behavior |
|---|---|
| Language server not on PATH | Skip Tier 2, use Tier 1, `confidence="heuristic"` |
| Tier 3 tool not on PATH (e.g. no `pyan3` installed) | `get_lld`/`get_hld` fall back to a Tier-1/Tier-2-derived approximation, `meta.degraded=True`, `meta.reason="pyan3 not found"` |
| LSP server crashes / times out mid-call | Restart once; on repeat failure, fall back one tier for that call only (server stays down for the session, logged once) |
| Requested file/symbol does not exist | Returns `RnaResult` with empty data + `meta.error="not_found"`, not an exception — callers branch on data, not exceptions |
| Path outside the repo root / path traversal | Raises `RnaSecurityError` — this **is** an invariant violation |
| `google_search` called without web opt-in configured | No network call is made; returns `RnaResult` with empty data and `meta.error="disabled"` — see `05_tool_contract_and_safety.md` §3 |

---

## 7. Concurrency model

- RNA methods are safe to call concurrently for read workloads; internal caches use per-key locks (compute-once-under-lock, other concurrent callers await the same in-flight result) rather than a single global lock, so an expensive `get_lld` on one module doesn't block a cheap `get_file` on another.
- LSP provider instances are one-per-language-server-per-repo (not one-per-call): started lazily on first use, kept warm for the process lifetime, shut down on session/process end.
- Tier 3 whole-program tools run as short-lived subprocesses invoked through a bounded worker pool, capped in parallelism to avoid saturating the host machine when several agents/tools call RNA at once.
