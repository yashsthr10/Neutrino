# RNA — Research & Analysis engine for coding agents

> **User-facing reference** (install, every method with inputs/outputs/examples, CLI, MCP): see the package [`../README.md`](../README.md).

## 1. What RNA is

RNA is a **standalone, on-demand knowledge API over a codebase**, built to be called by coding agents (LLM-driven or otherwise) exactly when they need one fact — "where is this symbol defined," "who calls this function," "what tests cover this file," "how does a request flow through this system" — instead of the agent (or its host system) pre-loading the whole repository into a prompt.

RNA is **not** an agent, an orchestrator, or a chat model wrapper. It never calls an LLM internally. It answers factual questions about a repository (and, for web search, about the outside world) with structured, bounded, cacheable data. Whatever agent runtime is driving the session — a custom agent loop, Claude Code, Cursor, an MCP client, a CI bot — decides *when* to call RNA and *what to do* with the answer.

It is designed to be embedded two ways:

1. **As a Python library**, imported directly into an agent's tool layer (`from rna import Rna`).
2. **As a standalone MCP server**, so any MCP-compatible agent can add RNA as a tool provider without any Python integration at all (`rna serve --repo .`).

Both surfaces are generated from one facade and one set of data contracts — see `05_tool_contract_and_safety.md`.

---

## 2. Why: what modern agentic coding systems actually ask for

Every serious coding agent today re-solves the same "understand the repo" problem, usually with one narrow technique:

| Need | Who solves it today, and how | RNA method(s) |
|---|---|---|
| Read a file / a slice of a file on demand | Claude Code, Cursor, Aider — plain file read tools | `get_file` |
| Find files by name/glob without loading them | All of the above (`fd`/glob tools) | `get_files_with_name` |
| Jump to a definition precisely | Sourcegraph Cody, Cursor (via LSP under the hood) | `get_symbol` |
| "Who calls this?" before changing a signature | Cursor, Sourcegraph precise code intel | `get_callers` |
| Module/file dependency graph | Aider's repo-map (tree-sitter + PageRank), `madge` | `get_import_graph` |
| "What tests cover this?" before editing | Manual, senior-engineer habit — no mainstream tool | `get_tests` |
| "What happens when X runs?" | Manual tracing — no mainstream agent tool does this well | `get_workflow` |
| Bird's-eye architecture understanding | Reading the README, manually | `get_hld` |
| Class/function-level structure of a module | `pyreverse`, `pyan`, doxygen, manual reading | `get_lld` |
| Fast literal/regex grep across the repo | Claude Code's primary discovery tool (ripgrep) | `search` |
| "Find code that *means* this" (no exact keyword) | Cursor's embedding index | `semantic_search` |
| External knowledge (library docs, error messages) | Devin, Cursor `@web`, browsing-enabled chat tools | `google_search` |

RNA's bet: combine **Claude Code's philosophy** (agentic, on-demand, tool-call-driven, no mandatory upfront index) with **Aider's repo-map insight** (structure derived from a real parser, not regexes), **Sourcegraph-grade precision** (language-server-backed go-to-definition and call hierarchy where available), and **Cursor-style semantic recall** (embeddings for fuzzy "where is the code that…" queries) — behind one facade, one cost model, and one degrade-gracefully policy, so it works identically whether the target repo is Python, TypeScript, Go, or C++.

---

## 3. Design principles

1. **On-demand, not eager.** No upfront "index the whole repo before you can do anything" pass. Every `rna.*` call is a lazy, individually cacheable unit of work; the first call to a new method on a new repo pays the cost, every call after (and every *other* method that happens to need the same underlying data) reuses it.
2. **Facade stability, swappable backends.** Callers use `rna.get_callers(...)`; whether the answer came from a language server, a whole-program static analyzer, or a text-search heuristic is an implementation detail hidden behind one interface (see `01_architecture.md` §2).
3. **Tiered precision, graceful degradation.** RNA never hard-fails because a language tool is missing on the host machine. It degrades through three tiers — structural → semantic → whole-program — and always reports a `confidence` level with the answer (`01_architecture.md` §3, `03_language_adapters.md`).
4. **Bounded by default.** Every response carries truncation and cost metadata. Reads, searches, and graph walks are capped by default (files, lines, result counts, depth) — callers opt into more, never get an unbounded response by accident.
5. **Cache-first, invalidation-aware.** Anything expensive (call graphs, embeddings, HLD/LLD diagrams) is computed once per `(file content hash, tool version)` and invalidated by content hash / git diff, never by wall-clock guesswork (`04_indexing_and_caching.md`).
6. **Deterministic core, no hidden LLM calls.** RNA never calls a chat/completion model. `semantic_search` uses a fixed embedding function (a vector encoder, not a generative model) — RNA answers "what is true," it never "reasons about what to do."
7. **Same shape for every language.** One facade, one set of return types, regardless of whether the repo is Python, TypeScript, Go, C/C++, or something RNA has no dedicated tooling for yet — the depth of the answer may vary (see confidence levels), the contract never does.
8. **Read-only, always.** RNA never writes to the repository and never mutates anything outside its own cache directory. It answers questions; it does not take actions.

---

## 4. Component ownership map

RNA is a facade composed of six focused engines. Every `rna.*` method is owned by exactly one (occasionally two, when a result is a ranked merge of two signals):

| Engine | Owns | Methods |
|---|---|---|
| **Repo Analyzer** | Filesystem/tree, raw file reads | `get_file`, `get_files_with_name` |
| **Graph Engine** | Symbol index, import graph, call graph, and its "Design Recovery" sub-component (HLD/LLD/workflow synthesis) | `get_symbol`, `get_import_graph`, `get_callers`, `get_workflow`, `get_hld`, `get_lld` |
| **Git Analyzer** | Commit history, co-change signal | feeds `get_tests` (secondary ranking signal) |
| **Search Engine** | Lexical/regex search | `search` |
| **Embedding Engine** | Semantic chunking + vector search | `semantic_search` |
| **Web Engine** | External knowledge, network egress boundary | `google_search` |

`get_tests` is a ranked merge: Graph Engine (reverse-import / naming-convention signals) + Git Analyzer (co-change history) — see `02_api_spec.md` §8.

---

## 5. Non-goals

- RNA does **not** decide when to call itself — that is the calling agent's job.
- RNA does **not** write to the repository. It is strictly read-only.
- RNA does **not** enforce a host system's token budget — it *helps* by returning already-bounded, already-cheap-to-truncate data, but a host agent's own context assembly is a separate concern outside RNA's scope.
- RNA does **not** require any language server or third-party binary to be installed to function at all — the structural tier (tree-sitter) always works; deeper tiers are opportunistic upgrades.
- RNA is **not** a general web browser. `google_search` returns snippets/links only; fetching and reading a URL's full content is a separate tool, not part of RNA v1.
- RNA does **not** ship its own agent loop, planner, or chat model integration. It is a tool provider, not a tool user.

---

## 6. Document index

| Doc | Contents |
|---|---|
| [`01_architecture.md`](01_architecture.md) | Component diagram, package layout, the three-tier language intelligence model, request lifecycle, degradation policy, concurrency model |
| [`02_api_spec.md`](02_api_spec.md) | Data models and the full contract (params/returns/errors/cost) for every `rna.*` method |
| [`03_language_adapters.md`](03_language_adapters.md) | The `LanguageProvider` protocol and the per-language tool matrix (pyan for Python LLD, and the equivalents for JS/TS, Go, C/C++) |
| [`04_indexing_and_caching.md`](04_indexing_and_caching.md) | On-demand computation model, two-tier cache, git-aware invalidation, performance budgets |
| [`05_tool_contract_and_safety.md`](05_tool_contract_and_safety.md) | Exposing RNA as agent tool-calls (function-calling schema) and as an MCP server, safety/egress rules, observability, testing strategy |
