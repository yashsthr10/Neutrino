# RNA — Research & Analysis for coding agents

On-demand, read-only knowledge API over a codebase. Agents call `rna.*` when they need a fact (definition, callers, tests, architecture) instead of dumping the whole repo into a prompt.

- **Library:** `from src.rna import Rna`
- **CLI:** `rna get-symbol ...` / `rna serve --stdio`
- **MCP:** every method exposed as `rna_<method>` tools

Deeper design docs live in [`docs/`](docs/). Optional language tools: [`TOOLS.md`](TOOLS.md).

---

## Install

From the NeutrinoCLI repo root:

```bash
pip install -e .

# optional upgrades
pip install -e '.[rna-python-lld]'   # pyan3 + pylint/pyreverse for richer LLD
pip install -e '.[rna-embeddings]'   # sentence-transformers for better semantic_search
```

Verify:

```bash
rna --help
```

---

## Quick start (library)

```python
from pathlib import Path
from src.rna import Rna, RnaConfig

# IMPORTANT: pass an absolute (or intentional) repo root — not cwd by accident
repo = Path("/path/to/your/repo").resolve()
rna = Rna(repo)

result = rna.get_symbol("parse_request", file_hint="pkg/parser.py")
print(result.data)          # list[SymbolRef]
print(result.meta.error)    # None | "not_found" | "disabled" | ...
print(result.meta.confidence)  # "heuristic" | "precise" | "whole_program" | None
```

With config:

```python
cfg = RnaConfig(
    repo_path=repo,
    web_search_enabled=False,
    embedding_model="hash",          # or "sentence-transformers"
    enabled_tiers=("structural", "semantic", "whole_program"),
)
rna = Rna(cfg)
```

---

## Common return shape

Every method returns `RnaResult[T]`:

| Field | Type | Meaning |
|---|---|---|
| `data` | `T` | Method-specific payload |
| `meta.cost_ms` | `float` | Wall time for the call |
| `meta.cache_hit` | `bool` | Served from cache |
| `meta.truncated` | `bool` | Result capped (lines, hits, depth, …) |
| `meta.confidence` | `str \| None` | `heuristic` / `precise` / `whole_program` when language tiers apply |
| `meta.degraded` | `bool` | Fell back (missing tool, hash embeddings, …) |
| `meta.reason` | `str \| None` | Why degraded / extra context |
| `meta.error` | `str \| None` | Soft error: `"not_found"`, `"disabled"`, … (not an exception) |
| `meta.tokens_estimate` | `int` | Rough size hint for context budgeting |

```python
result.to_dict()  # JSON-serializable {"data": ..., "meta": {...}}
```

**Exceptions (rare):** `RnaSecurityError` for path escape; other misses use `meta.error`.

---

## Method index

| Method | One-line purpose |
|---|---|
| [`get_file`](#1-get_file) | Read a file / line slice |
| [`get_files_with_name`](#2-get_files_with_name) | Find paths by name/glob |
| [`get_symbol`](#3-get_symbol) | Go-to-definition |
| [`get_import_graph`](#4-get_import_graph) | File/module import edges |
| [`get_callers`](#5-get_callers) | Who calls this symbol? |
| [`get_tests`](#6-get_tests) | Tests covering a file/symbol |
| [`get_workflow`](#7-get_workflow) | Trace calls from an entrypoint |
| [`get_hld`](#8-get_hld) | High-level architecture map |
| [`get_lld`](#9-get_lld) | Low-level structure of a scope |
| [`search`](#10-search) | Literal/regex grep |
| [`semantic_search`](#11-semantic_search) | Meaning-based code search |
| [`google_search`](#12-google_search) | External web search (opt-in) |

Helpers: [`invalidate`](#helpers), [`warm`](#helpers).

---

## 1. `get_file`

Read a repo-relative file, optionally a line range.

### Signature

```python
get_file(path: str, *, start_line: int | None = None, end_line: int | None = None) -> RnaResult[FileSlice | None]
```

### Input

| Param | Required | Description |
|---|---|---|
| `path` | yes | Repo-relative path (`"pkg/parser.py"`) |
| `start_line` | no | 1-indexed inclusive start |
| `end_line` | no | 1-indexed inclusive end |

If both line args are omitted and the file is longer than `max_lines_per_file` (default **200**), content is truncated.

### Output (`data`: `FileSlice | None`)

| Field | Type | Description |
|---|---|---|
| `path` | `str` | Repo-relative path |
| `start_line` / `end_line` | `int` | Slice bounds |
| `content` | `str` | Text returned |
| `total_lines` | `int` | Full file line count |
| `truncated` | `bool` | Cap applied |

`meta.error = "not_found"` if missing. Path escape → `RnaSecurityError`.

### Usage

```python
r = rna.get_file("pkg/parser.py")
r = rna.get_file("pkg/parser.py", start_line=1, end_line=40)
print(r.data.content if r.data else r.meta.error)
```

---

## 2. `get_files_with_name`

Find file paths without reading contents.

### Signature

```python
get_files_with_name(pattern: str, *, limit: int = 50) -> RnaResult[list[str]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `pattern` | yes | Exact name, substring, fuzzy, or glob (`"**/test_*.py"`) |
| `limit` | no | Max paths (default 50) |

### Output (`data`: `list[str]`)

Repo-relative paths, ranked: exact basename → prefix → fuzzy, then shallower paths first.

### Usage

```python
r = rna.get_files_with_name("parser")
r = rna.get_files_with_name("**/test_*.py", limit=20)
for path in r.data:
    print(path)
```

---

## 3. `get_symbol`

Resolve a symbol to its definition site(s).

### Signature

```python
get_symbol(name: str, *, file_hint: str | None = None) -> RnaResult[list[SymbolRef]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `name` | yes | Symbol or dotted name (`"parse_request"`, `"Router.parse_request"`) |
| `file_hint` | no | Narrow search to one file (strongly recommended) |

### Output (`data`: `list[SymbolRef]`)

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Symbol name |
| `kind` | `str` | `function` / `method` / `class` / `interface` / `struct` / `variable` / `constant` |
| `file` | `str` | Repo-relative path |
| `line_start` / `line_end` | `int` | Definition span |
| `signature` | `str \| None` | When available |
| `docstring` | `str \| None` | When available |
| `language` | `str` | e.g. `"python"` |

`meta.confidence`: `heuristic` (tree-sitter) / `precise` (LSP) / `whole_program`.  
`meta.error = "not_found"` if empty.

### Usage

```python
r = rna.get_symbol("parse_request", file_hint="pkg/parser.py")
if r.data:
    s = r.data[0]
    print(f"{s.file}:{s.line_start}-{s.line_end} ({s.kind})")
```

---

## 4. `get_import_graph`

File/module-level “what imports what”.

### Signature

```python
get_import_graph(scope: str | None = None) -> RnaResult[ImportGraph]
```

### Input

| Param | Required | Description |
|---|---|---|
| `scope` | no | Limit to file/dir/package; `None` = repo-wide |

### Output (`data`: `ImportGraph`)

| Field | Type | Description |
|---|---|---|
| `scope` | `str \| None` | Echo of input scope |
| `edges` | `tuple[ImportEdge, ...]` | Dependency edges |

**`ImportEdge`**

| Field | Type | Description |
|---|---|---|
| `from_file` | `str` | Importer path |
| `to` | `str` | Resolved path or external module name |
| `external` | `bool` | Outside repo |
| `symbols` | `tuple[str, ...]` | Imported names when known |

### Usage

```python
g = rna.get_import_graph(scope="pkg")
for e in g.data.edges:
    print(f"{e.from_file} -> {e.to} (external={e.external})")
```

---

## 5. `get_callers`

Reverse call graph — who invokes this symbol.

### Signature

```python
get_callers(symbol: str, *, file_hint: str | None = None, limit: int = 25) -> RnaResult[list[CallEdge]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `symbol` | yes | Callee name |
| `file_hint` | no | Definition file hint |
| `limit` | no | Max edges (default 25) |

### Output (`data`: `list[CallEdge]`)

| Field | Type | Description |
|---|---|---|
| `caller` | `SymbolRef` | Calling function/method |
| `callee_name` | `str` | Symbol that was called |
| `call_site_line` | `int` | Line of the call |

`meta.truncated=True` if more callers exist than `limit`.  
Tier-1 name match may include false positives (`confidence="heuristic"`).

### Usage

```python
r = rna.get_callers("parse_request", file_hint="pkg/parser.py")
for edge in r.data:
    print(f"{edge.caller.file}:{edge.call_site_line} {edge.caller.name}()")
```

---

## 6. `get_tests`

Find tests linked to a file or symbol.

### Signature

```python
get_tests(target: str) -> RnaResult[list[TestLink]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `target` | yes | File path or symbol name |

### Output (`data`: `list[TestLink]`)

| Field | Type | Description |
|---|---|---|
| `test_file` | `str` | Test file path |
| `test_symbol` | `SymbolRef \| None` | Specific test when known |
| `target` | `str` | Echo of input |
| `relation` | `str` | `direct_import` / `naming_convention` / `co_change` |
| `confidence` | `float` | Ranking score 0–1 (not the tier Confidence enum) |

Ranked highest confidence first.

### Usage

```python
r = rna.get_tests("pkg/parser.py")
for t in r.data:
    print(t.test_file, t.relation, t.confidence)
```

---

## 7. `get_workflow`

Forward call trace from an entrypoint (“what happens when X runs?”).

### Signature

```python
get_workflow(entrypoint: str, *, max_depth: int = 4) -> RnaResult[WorkflowTrace]
```

### Input

| Param | Required | Description |
|---|---|---|
| `entrypoint` | yes | Symbol name, or `file:symbol` / `file:line` style hint |
| `max_depth` | no | BFS depth (hard-capped by config, default max 6) |

### Output (`data`: `WorkflowTrace`)

| Field | Type | Description |
|---|---|---|
| `entrypoint` | `str` | Echo of input |
| `steps` | `tuple[WorkflowStep, ...]` | Depth-ordered steps |
| `truncated_by_depth` | `bool` | Walk hit depth cap |

**`WorkflowStep`:** `symbol` (`SymbolRef`), `depth` (`int`), `call_site_line` (`int | None`).

### Usage

```python
r = rna.get_workflow("handle", max_depth=3)
for step in r.data.steps:
    indent = "  " * step.depth
    print(f"{indent}{step.symbol.name} @ {step.symbol.file}")
```

---

## 8. `get_hld`

High-level design: packages/modules and dependencies between them.

### Signature

```python
get_hld(*, scope: str | None = None, format: Literal["json", "mermaid"] = "json") -> RnaResult[HLDModel]
```

### Input

| Param | Required | Description |
|---|---|---|
| `scope` | no | Limit to subtree (e.g. `"src/"`) |
| `format` | no | `"json"` (default) or `"mermaid"` (also fills diagram string) |

### Output (`data`: `HLDModel`)

| Field | Type | Description |
|---|---|---|
| `nodes` | `tuple[HLDNode, ...]` | Packages / modules / externals |
| `edges` | `tuple[HLDEdge, ...]` | Aggregated deps with `weight` |
| `mermaid` | `str \| None` | Diagram when `format="mermaid"` |

**`HLDNode`:** `id`, `kind` (`package`/`module`/`external_dependency`), `entrypoint` (`bool`).  
**`HLDEdge`:** `from_id`, `to_id`, `weight` (`int`).

### Usage

```python
r = rna.get_hld(scope="pkg", format="mermaid")
print(r.data.mermaid)
for e in r.data.edges:
    print(e.from_id, "->", e.to_id, e.weight)
```

---

## 9. `get_lld`

Low-level design for one file/module: classes, functions, calls, inheritance.

### Signature

```python
get_lld(scope: str, *, format: Literal["json", "mermaid"] = "json") -> RnaResult[LLDModel]
```

### Input

| Param | Required | Description |
|---|---|---|
| `scope` | yes | File or directory path (never whole-repo by default) |
| `format` | no | `"json"` or `"mermaid"` |

### Output (`data`: `LLDModel`)

| Field | Type | Description |
|---|---|---|
| `scope` | `str` | Echo of input |
| `nodes` | `tuple[LLDNode, ...]` | Symbols in scope |
| `edges` | `tuple[LLDEdge, ...]` | `calls` / `inherits` / `composes` / `implements` |
| `mermaid` | `str \| None` | Optional diagram |

Without Tier-3 tools (e.g. `pyan3`), returns a structural approximation with `meta.degraded=True`.

### Usage

```python
r = rna.get_lld("pkg/parser.py", format="json")
print("degraded:", r.meta.degraded, r.meta.reason)
for n in r.data.nodes:
    print(n.node_kind, n.symbol.name)
```

---

## 10. `search`

Fast literal/regex grep across the repo.

### Signature

```python
search(query: str, *, glob: str | None = None, limit: int = 50, regex: bool = False) -> RnaResult[list[SearchHit]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `query` | yes | Text to find |
| `glob` | no | Path filter (`"src/**/*.py"`) |
| `limit` | no | Max hits (default 50) |
| `regex` | no | Treat `query` as regex (default `False`) |

Uses `rg` when available; otherwise Python `re` (`meta.degraded=True`).

### Output (`data`: `list[SearchHit]`)

| Field | Type | Description |
|---|---|---|
| `file` | `str` | Path |
| `line` | `int` | Line number |
| `snippet` | `str` | Matching line text |
| `match` | `str` | Query echo |

### Usage

```python
r = rna.search("parse_request", glob="**/*.py")
for h in r.data:
    print(f"{h.file}:{h.line}: {h.snippet}")
```

---

## 11. `semantic_search`

Find code by meaning when you don’t know the exact name.

### Signature

```python
semantic_search(query: str, *, limit: int = 10) -> RnaResult[list[SemanticHit]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `query` | yes | Natural-language description |
| `limit` | no | Max hits (default 10) |

Default embedding model is offline `"hash"` (`meta.degraded=True`). Install `rna-embeddings` and set `embedding_model="sentence-transformers"` for better quality. First call builds an index (can be slow); use `rna.warm()`.

### Output (`data`: `list[SemanticHit]`)

| Field | Type | Description |
|---|---|---|
| `file` | `str` | Path |
| `symbol` | `str \| None` | Chunk symbol if known |
| `start_line` / `end_line` | `int` | Chunk span |
| `snippet` | `str` | Chunk text (truncated) |
| `score` | `float` | Similarity score |

### Usage

```python
r = rna.semantic_search("split request string into tokens", limit=5)
for h in r.data:
    print(f"{h.score:.3f} {h.file}:{h.start_line} {h.symbol}")
```

---

## 12. `google_search`

External web search (docs, errors, APIs). **Disabled by default.**

### Signature

```python
google_search(query: str, *, limit: int = 5) -> RnaResult[list[WebResult]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `query` | yes | Web query |
| `limit` | no | Max results (default 5) |

Requires `RnaConfig(web_search_enabled=True)` plus provider credentials when using Google CSE (`web_search_api_key`, `web_search_cx`), or `web_search_provider="duckduckgo"`.

### Output (`data`: `list[WebResult]`)

| Field | Type | Description |
|---|---|---|
| `title` | `str` | Result title |
| `url` | `str` | Link |
| `snippet` | `str` | Short text |
| `source` | `str` | Provider id |
| `fetched_at` | `str` | ISO-8601 timestamp |

If disabled: `data=[]`, `meta.error="disabled"` (no network call).

### Usage

```python
from src.rna import Rna, RnaConfig

rna = Rna(RnaConfig(repo_path=repo, web_search_enabled=True, web_search_provider="duckduckgo"))
r = rna.google_search("python pathlib resolve symlink")
for w in r.data:
    print(w.title, w.url)
```

---

## Helpers

### `invalidate(path=None)`

Clear cache for one path or everything (after external edits).

```python
rna.invalidate("pkg/parser.py")
rna.invalidate()  # all
```

### `warm(only="embeddings")`

Pre-build the semantic index so the first `semantic_search` is faster.

```python
rna.warm(only="embeddings")
```

---

## CLI

```bash
# help
rna --help
rna get-symbol --help

# one-shot queries (--repo after the subcommand is supported)
rna get-symbol parse_request --repo /path/to/repo --file-hint pkg/parser.py
rna get-file pkg/parser.py --repo /path/to/repo
rna search parse_request --repo /path/to/repo
rna warm --repo /path/to/repo --only embeddings

# MCP over stdio (blocks on stdin — expected)
rna serve --repo /path/to/repo --stdio

# MCP over TCP
rna serve --repo /path/to/repo --port 7411

# enable web search for the serve process
rna serve --repo /path/to/repo --stdio --web
```

CLI JSON output matches `RnaResult.to_dict()`.

---

## MCP tools

`rna serve` registers these tools (same schemas as the library):

| MCP tool name | Maps to |
|---|---|
| `rna_get_symbol` | `get_symbol` |
| `rna_get_file` | `get_file` |
| `rna_get_files_with_name` | `get_files_with_name` |
| `rna_get_import_graph` | `get_import_graph` |
| `rna_get_callers` | `get_callers` |
| `rna_get_tests` | `get_tests` |
| `rna_get_workflow` | `get_workflow` |
| `rna_get_hld` | `get_hld` |
| `rna_get_lld` | `get_lld` |
| `rna_search` | `search` |
| `rna_semantic_search` | `semantic_search` |
| `rna_google_search` | `google_search` |

---

## When to use which

| Goal | Method |
|---|---|
| Where is this defined? | `get_symbol` |
| Read code | `get_files_with_name` → `get_file` |
| Who calls this? | `get_callers` |
| Module dependencies | `get_import_graph` |
| Related tests | `get_tests` |
| Trace a request/CLI path | `get_workflow` |
| Package-level map | `get_hld` |
| One-module internals | `get_lld` |
| Grep a string | `search` |
| Find by meaning | `semantic_search` |
| Outside docs / errors | `google_search` |

---

## Config reference (`RnaConfig`)

| Field | Default | Notes |
|---|---|---|
| `repo_path` | required | Absolute root of the analyzed repo |
| `cache_dir` | `<repo>/.rna_cache` | L2 disk cache |
| `enabled_tiers` | all three | `structural` / `semantic` / `whole_program` |
| `max_lines_per_file` | `200` | `get_file` default cap |
| `max_callers` | `25` | Default `get_callers` limit |
| `max_workflow_depth` | `6` | Hard cap for workflow BFS |
| `web_search_enabled` | `False` | Must opt in for `google_search` |
| `web_search_provider` | `"google_cse"` | or `"duckduckgo"` |
| `embedding_model` | `"hash"` | or `"sentence-transformers"` |
| `cache_enabled` | `True` | Disable for always-fresh (slower) |

---

## Precision tiers (short)

| Tier | Needs | Improves |
|---|---|---|
| 1 Structural | tree-sitter (always) | Always available |
| 2 Semantic | LSP on PATH (`pylsp`, `gopls`, …) | Precise `get_symbol` / `get_callers` |
| 3 Whole-program | `pyan3`, `madge`, … | Richer `get_lld` / bulk graphs |

Missing tools never crash the API — results degrade and set `meta.degraded` / lower `confidence`. Details: [`TOOLS.md`](TOOLS.md).

---

## Design docs

| Doc | Contents |
|---|---|
| [`docs/README.md`](docs/README.md) | Vision & principles |
| [`docs/01_architecture.md`](docs/01_architecture.md) | Package layout, tiers, lifecycle |
| [`docs/02_api_spec.md`](docs/02_api_spec.md) | Full wire contract |
| [`docs/03_language_adapters.md`](docs/03_language_adapters.md) | Per-language tool matrix |
| [`docs/04_indexing_and_caching.md`](docs/04_indexing_and_caching.md) | Cache & budgets |
| [`docs/05_tool_contract_and_safety.md`](docs/05_tool_contract_and_safety.md) | MCP, safety, testing |
