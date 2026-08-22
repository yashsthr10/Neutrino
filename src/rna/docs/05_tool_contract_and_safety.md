# RNA — Tool Contract, MCP Server, Safety & Testing

## 1. Exposing RNA as agent tool-calls (in-process)

When RNA is imported directly into a host agent's tool layer, each `rna.*` method is registered as one callable tool using the same function-calling schema shape most chat-model APIs expect (OpenAI/Anthropic-style JSON schema for parameters). `rna/mcp/schema.py` generates this schema **from the method signatures themselves** (via type hints), so the schema can never drift from the actual contract in `02_api_spec.md`.

Example generated schema for `get_callers`:

```json
{
  "name": "rna_get_callers",
  "description": "Return every call site that invokes the given symbol (reverse call graph).",
  "parameters": {
    "type": "object",
    "properties": {
      "symbol": { "type": "string", "description": "Symbol name, e.g. 'Router.parse_request'." },
      "file_hint": { "type": "string", "description": "Optional file path to disambiguate.", "nullable": true },
      "limit": { "type": "integer", "default": 25 }
    },
    "required": ["symbol"]
  }
}
```

The tool's return value (serialized `RnaResult`) is passed back to the model as the tool result exactly as-is — a host agent does not need a translation layer, only a call to `rna.tools_schema.all()` to get every schema at once and a dispatcher that maps `name -> Rna` method.

---

## 2. Exposing RNA as an MCP server

For any agent runtime that speaks the [Model Context Protocol](https://modelcontextprotocol.io) (Claude Code, Cursor, and a growing set of MCP-compatible clients), RNA ships a standalone server:

```bash
rna serve --repo /path/to/target/repo --port 7411
# or, for stdio-based MCP clients:
rna serve --repo /path/to/target/repo --stdio
```

`rna/mcp/server.py` is a thin JSON-RPC adapter: it registers every `rna.*` method as an MCP `tool`, using the exact same schema generation as §1, and forwards each MCP `tools/call` request to the one shared `Rna` facade instance for that server process. There is no second implementation to keep in sync — this is the same reasoning as the "one facade, two surfaces" design in `01_architecture.md` §1.

This means a single `rna serve` process, pointed at a checked-out repository, immediately gives **any** MCP-compatible agent — not just ones built on this codebase — access to `get_symbol`, `get_callers`, `get_hld`, `get_lld`, and the rest, without that agent's authors writing any repo-analysis code of their own. This is the intended "modern agentic coding system" integration point: RNA becomes infrastructure other tools can plug into, not a feature bolted onto one specific agent.

---

## 3. Safety

RNA's safety boundary is narrower than a general tool layer's (it never edits files or runs arbitrary shell commands), but it still enforces:

| Rule | Enforcement |
|---|---|
| No path escapes the repo root | Every path parameter is resolved and checked against the repo root before any filesystem access; violations raise `RnaSecurityError` immediately, not degrade silently (`01_architecture.md` §6) |
| No symlink escapes | Resolved paths are checked post-symlink-resolution, not just lexically |
| No arbitrary command execution | Every subprocess RNA spawns (LSP servers, Tier 3 tools) is from a fixed allowlist of known binaries with fixed argument templates — never a caller-supplied command string |
| Network egress is opt-in and explicit | `google_search` is disabled by default (`RnaConfig.web_search_enabled=False`); enabling it is a deliberate configuration act, not a default, and every call is logged as a distinct "network egress" event (see §4) |
| Web results are data, not executable instructions | `WebResult.snippet`/`title` are returned as plain strings; RNA does not fetch or render arbitrary URL content (explicit non-goal, `README.md` §5) |
| Cache is process/machine-local only | `.rna_cache/` is never transmitted anywhere; it is a local performance optimization, not a data store with its own access-control surface |

---

## 4. Observability

Every `rna.*` call — regardless of surface (in-process or MCP) — emits one structured log record:

```python
{
    "method": "get_callers",
    "params_summary": "symbol=Router.parse_request",
    "cost_ms": 42.1,
    "cache_hit": False,
    "confidence": "precise",
    "degraded": False,
    "backend_tier": "lsp:pylsp",
    "network_egress": False,
}
```

`google_search` calls additionally log `"network_egress": True` plus the destination provider (not the full query, to avoid leaking sensitive repo-derived context into logs by default — configurable for debugging). This gives a host application (or a human auditing a session) a complete, tier-labeled trace of every fact an agent gathered and how expensive/confident each one was — the same observability-first stance the rest of a disciplined agent system should have around its tool layer.

---

## 5. Testing strategy

| Layer | Approach |
|---|---|
| Facade contract | One test suite run against `FakeRna` *and* the real `Rna` (parametrized), asserting both satisfy `RnaPort` identically in shape (not content) — guarantees a host application's tests never need real language tools installed |
| Tier 1 (tree-sitter) | Golden-file tests: a small fixture repo per language, with hand-verified expected `SymbolRef`/`ImportEdge` lists |
| Tier 2 (LSP) | Integration tests behind a `pytest` marker requiring the actual language server on PATH; skipped (not failed) in environments without it, mirroring the "never hard-fail on missing tools" philosophy at the test level too |
| Tier 3 (whole-program tools) | Same skip-if-missing marker; golden `LLDModel`/`HLDModel` snapshots per fixture repo, regenerated deliberately (not silently) when a tool's output format changes |
| Cache/invalidation | Unit tests simulate file content changes and assert exact invalidation scope (only affected keys are evicted, nothing over-invalidated) |
| MCP server | Contract tests using a minimal MCP client against `rna serve --stdio`, asserting schema and response shape match the in-process facade byte-for-byte after JSON round-trip |

`FakeRna` (scripted, deterministic, zero subprocesses) in `tests/doubles/rna.py` is the default dependency for unit tests — fast, deterministic, and safe to run in CI with no external tooling installed.
