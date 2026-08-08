# RNA — Language Adapters

## 1. The `LanguageProvider` protocol

Every tier, for every language, implements the same narrow protocol. RNA's graph/symbol methods never call a tool directly — they call whatever `LanguageProvider` the registry hands them for the language in question.

```python
# rna/adapters/base.py
from __future__ import annotations

from typing import Protocol

class LanguageProvider(Protocol):
    """One tier's capability for one language. Never raises for 'not found' -- returns empty."""

    language: str
    tier: str  # "structural" | "semantic" | "whole_program"

    def is_available(self) -> bool:
        """Cheap probe, called once and cached by the registry (e.g. `shutil.which(...)`)."""
        ...

    def find_symbol(self, name: str, file_hint: str | None) -> list["SymbolRef"]: ...
    def find_imports(self, file_path: str) -> list["ImportEdge"]: ...
    def find_callers(self, symbol: str, file_hint: str | None) -> list["CallEdge"]: ...
    def find_callees(self, symbol: str, file_hint: str | None) -> list["CallEdge"]: ...

    def build_whole_program_graph(self, scope: str) -> "WholeProgramGraph | None":
        """Tier 3 only: returns None for Tier 1/2 providers."""
        ...
```

Not every provider implements every method meaningfully — a Tier 1 tree-sitter provider's `find_callers` is a heuristic text match; a Tier 3 provider's `find_symbol` may simply delegate to Tier 1 since whole-program tools are usually graph exporters, not point-query tools. The registry composes results across the chain rather than assuming one provider does everything (see §4).

---

## 2. Tier 1 — Structural (tree-sitter)

**Always available.** Requires the `tree-sitter` Python bindings plus the grammar package for each language present in the repo (installed as ordinary dependencies, no external process, no network, no build step).

| Extracts | How |
|---|---|
| Symbol definitions | Walk the syntax tree for `function_definition` / `class_definition` / `method_definition` node types (grammar-specific node names, normalized to RNA's `SymbolRef.kind`) |
| Import/require statements | Walk for `import_statement` / `import_from_statement` (Python), `import_declaration` (JS/TS/Go), `preproc_include` (C/C++) |
| Rough call sites | Walk for `call_expression` nodes, match the callee identifier text against the target symbol name — this is a **name match**, not a resolved reference, hence `confidence="heuristic"` |

Tree-sitter is also the backbone of `semantic_search`'s chunking (chunk boundaries = function/class node ranges, not fixed-size windows) and of `get_files_with_name`'s language-aware ranking (e.g. treating `Router` and `router` as the same basename family across languages with different casing conventions).

Grammar coverage used by RNA v1: Python, JavaScript, TypeScript/TSX, Go, C, C++, Java, Rust, Ruby — extendable by adding a grammar dependency; no code changes required outside `registry.py`'s language-to-grammar map.

---

## 3. Tier 2 — Semantic (Language Server Protocol)

**Opportunistic.** One generic LSP client (`rna/adapters/lsp_provider.py`) speaks JSON-RPC over stdio to whichever server is configured for a language. This is a single adapter for many backends:

| Language | Server RNA looks for on PATH | LSP methods used |
|---|---|---|
| Python | `pylsp` or `pyright-langserver` (first found wins; configurable) | `textDocument/definition`, `textDocument/references`, `callHierarchy/incomingCalls`, `callHierarchy/outgoingCalls`, `workspace/symbol` |
| JavaScript / TypeScript | `typescript-language-server` | same four methods |
| Go | `gopls` | same four methods (`gopls` implements call hierarchy natively) |
| C / C++ | `clangd` | same four methods (requires a `compile_commands.json`; RNA looks for one and degrades to Tier 1 if absent, since `clangd` without compile flags gives poor results) |
| Rust | `rust-analyzer` | same four methods |
| Java | `jdtls` | same four methods |

Lifecycle: on first request for a language, RNA spawns the server, performs the `initialize`/`initialized` handshake against the repo root, and keeps it warm for the process lifetime (see `01_architecture.md` §7). Files are synced via `textDocument/didOpen` on demand — RNA does not open every file in the repo, only the ones a query actually touches, preserving the on-demand principle even inside Tier 2.

`get_symbol` and `get_callers` prefer Tier 2 whenever the server is up: it is not a heuristic, it is the same machinery a human's IDE uses, so results are type-aware (correctly distinguishes overloaded functions, resolves aliased imports, ignores comments/strings that merely mention a name).

---

## 4. Tier 3 — Whole-program (per-language static analyzers)

**Opportunistic, and the direct answer to "for LLD python we use pyan, for other languages their respective tools."** These tools export a whole-repo (or whole-scope) graph/diagram in one pass, which is exactly what `get_hld`, `get_lld`, and *bulk* `get_import_graph`/`get_callers` need — spending N Tier-2 point-queries to reconstruct the same graph would be both slower and noisier.

| Language | Tool(s) | Produces | Notes |
|---|---|---|---|
| Python | **`pyan3`** | Whole-repo function/method call graph (dot/JSON) | Primary LLD call-graph source; static-analysis based, no execution required |
| Python | `pyreverse` (part of `pylint`) | Class diagrams: inheritance, attributes, associations | Merged with `pyan3`'s call edges into one `LLDModel` (see `02_api_spec.md` §11) |
| Python | `pycg` (optional, higher precision) | Whole-program call graph via points-to analysis | Preferred over `pyan3` when installed — more accurate on dynamic dispatch, slower |
| JavaScript / TypeScript | `madge` | Module dependency graph (also detects circular deps) | Used for `get_import_graph` bulk mode and as an `get_hld` input |
| JavaScript / TypeScript | `dependency-cruiser` | Rule-aware dependency graph | Alternate/validating source for the same graph shape as `madge` |
| JavaScript / TypeScript | `ts-morph` (TS Compiler API wrapper) | Class structure, in-scope call edges | Drives `get_lld` for TS/JS scopes |
| Go | `golang.org/x/tools/go/callgraph` (via `go/packages`) | Whole-program call graph | Same family of tooling used by `guru`/`gopls` internally |
| Go | `gopls` call hierarchy (batched) | Call graph for a bounded scope | Reused from the Tier 2 server when already running, avoiding a second process for small scopes |
| C / C++ | `clangd` call hierarchy (batched across a scope) | Function-level call graph | Requires `compile_commands.json`, same as Tier 2 |
| C / C++ | `cscope` / `universal-ctags` | Symbol index + rough cross-reference | Fallback when no compile database exists |
| Any language without a Tier 3 tool | Tier 1/2-derived approximation | Best-effort `LLDModel`/`HLDModel`, `meta.degraded=True` | Never a hard failure — see `01_architecture.md` §6 |

Tier 3 tools run as short-lived subprocesses with a parsed-output adapter that normalizes each tool's native format (dot, JSON, or tool-specific text) into RNA's `LLDModel`/`HLDModel`/`CallEdge` shapes, so the rest of the system never sees a tool-specific format.

---

## 5. Registry: resolving a provider chain

```python
# rna/adapters/registry.py (shape, not full implementation)

LANGUAGE_TOOLS: dict[str, dict[str, list[str]]] = {
    "python":     {"lsp": ["pylsp", "pyright-langserver"], "tier3": ["pycg", "pyan3", "pyreverse"]},
    "typescript": {"lsp": ["typescript-language-server"],  "tier3": ["madge", "ts-morph", "dependency-cruiser"]},
    "javascript": {"lsp": ["typescript-language-server"],  "tier3": ["madge", "dependency-cruiser"]},
    "go":         {"lsp": ["gopls"],                        "tier3": ["go-callgraph"]},
    "cpp":        {"lsp": ["clangd"],                        "tier3": ["clangd", "cscope", "ctags"]},
    "c":          {"lsp": ["clangd"],                        "tier3": ["clangd", "cscope", "ctags"]},
    "rust":       {"lsp": ["rust-analyzer"],                 "tier3": []},
    "java":       {"lsp": ["jdtls"],                          "tier3": []},
}

def resolve(language: str) -> list[LanguageProvider]:
    """Tier 1 provider is always included. Tier 2/3 appended only if a probe succeeds.
    Probe results are cached for the process lifetime -- re-probed only on explicit
    config reload, never on a per-call basis."""
```

Language detection for a given file is by extension first (`.py`, `.ts`, `.go`, `.cpp`, …), with a shebang/content sniff fallback for extensionless scripts. A repo with multiple languages (e.g. a Python backend + TypeScript frontend) gets independent provider chains per language — RNA does not assume a mono-language repo anywhere in its design.

---

## 6. Adding a new language

1. Add (or confirm) a tree-sitter grammar dependency for the language — Tier 1 support is immediate.
2. If an LSP server exists for the language, add it to `LANGUAGE_TOOLS[<lang>]["lsp"]` — Tier 2 support is immediate (the generic client needs no per-language code).
3. If precise `get_hld`/`get_lld` quality matters for that language, add a small output-parsing adapter in `rna/adapters/<lang>_tools.py` that normalizes one whole-program tool's output into `LLDModel`/`HLDModel`/`CallEdge` — this is the only genuinely per-language code RNA ever needs.
4. No changes are required to `facade.py`, `models.py`, or any `rna.*` method signature — the three-tier model exists precisely so that adding language coverage never touches the public contract.
