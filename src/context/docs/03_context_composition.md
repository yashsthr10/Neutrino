# Context Manager — Composition Pipeline

This is the internal pipeline named in `01_architecture.md` §4, one section per stage. Every stage is a small, independently testable class; `manager/context_manager.py` is a thin composer of all seven, exactly the way `rna/facade.py` composes six engines without containing engine logic itself.

```text
ContextRequest
      │
      ▼
Requirement Analysis   (analyzer.py)
      │
      ▼
Retrieval Planning      (retrieval_planner.py)  ──►  RNA + Conversation Manager
      │
      ▼
Aggregation              (aggregator.py)
      │
      ▼
Ranking                    (ranker.py)
      │
      ▼
Compression                  (compressor.py)
      │
      ▼
Validation                     (validator.py)
      │
      ▼
ContextPackage
```

---

## 1. Cache check (before any of the above)

`resolve()`'s first action, before Requirement Analysis even runs, is a cache lookup keyed on:

```text
(repo_fingerprint, conversation_state_hash, request_fingerprint)
```

- `repo_fingerprint` — reuses RNA's own fingerprint function (`src/rna/repo_analyzer/fingerprint.py`) rather than recomputing an equivalent hash; the Context Manager asks RNA for its current fingerprint instead of re-deriving repository staleness itself (**Reuse Over Reinvention**).
- `conversation_state_hash` — the Conversation Manager's current message-log length + latest summary id, so a package is invalidated the moment new conversation turns exist, without needing a TTL.
- `request_fingerprint` — a content hash of the `ContextRequest` itself.

A hit skips every remaining stage entirely — no RNA calls, no Conversation Manager query, zero cost beyond the cache lookup itself.

---

## 2. Requirement Analysis

**Class:** `analyzer.RequirementAnalyzer`
**Input:** `ContextRequest`
**Output:** `RetrievalPlan` — an ordered list of `(rna_method_name, kwargs)` pairs, plus a flag for whether Conversation Manager retrieval should run.

This stage answers "given this task, which facts are worth fetching" — and it answers it with a **deterministic rule table**, not an LLM call, for the same reason the Intelligence Engine's Deterministic Router is deterministic (`docs/03_architecture.md` §4.3): retrieval cost must be predictable and auditable, not a per-call judgment call.

If `request.capabilities` is set, the table is bypassed entirely — the caller already knows what it needs.

### Default rule table

| `requesting_agent` | `task_complexity` | Planned RNA calls |
|---|---|---|
| `planner` | `SIMPLE` | `get_files_with_name` (from hints) + `get_file` per hint |
| `planner` | `MEDIUM` | + `get_symbol`/`get_callers` for `symbol_hints`, `get_import_graph(scope=hint_dir)`, `get_tests(hint)` |
| `planner` | `COMPLEX` | + `get_hld(scope=hint_dir)`, `get_workflow(entrypoint=...)` if an entrypoint hint is present |
| `coder` | any | `get_file` per hint (full content, no compression preference), `get_symbol` for `symbol_hints`, `get_callers` for symbols about to be renamed/changed |
| `verifier` | any | `get_tests(hint)`, `get_file` for the modified files only (from `ExecutionState.code_changes`, passed via `file_hints`) |
| `reviewer` | any | `get_file` for modified files + `get_callers` for changed public symbols (blast-radius check) |

Every `requesting_agent` always triggers a Conversation Manager query (`retrieve` + `get_recent` + `get_decisions`) — conversational memory is cheap relative to RNA calls and is never gated by complexity.

This table lives in code as data (a `dict`/`match` keyed by `(requesting_agent, task_complexity)`), not as scattered `if` statements, so it is reviewable and testable as a single artifact — a golden-file test asserts the exact planned call list for every `(requesting_agent, task_complexity)` combination.

---

## 3. Retrieval Planning

**Class:** `retrieval_planner.RetrievalPlanner`
**Input:** `RetrievalPlan`
**Output:** raw `RnaResult` list + raw `ConversationContext`

Executes the plan from Requirement Analysis:

1. Applies per-call limits from `ContextConfig` (`retrieval_timeout_ms`) — any single `rna.*` call that exceeds its timeout is treated the same way RNA treats a Tier 2/3 timeout: the call is abandoned, not retried indefinitely, and the gap is recorded (`01_architecture.md` §5).
2. Fires the RNA batch and the Conversation Manager query concurrently against a bounded worker pool (`01_architecture.md` §6) — neither depends on the other.
3. Never fires the same `(method, kwargs)` pair twice within one plan (de-duplicates before dispatch) — e.g. if both the `planner` and `MEDIUM` rules would call `get_file` on the same hint, it is requested once.

This is the only stage that holds a live `RnaPort` reference. No other Context Subsystem component, and no component outside the Context Subsystem, is given one.

---

## 4. Aggregation

**Class:** `aggregator.Aggregator`
**Input:** raw `RnaResult` list + raw `ConversationContext`
**Output:** flat `list[RepositoryContextItem]` + the `ConversationContext` unchanged

Aggregation's only job is *shape normalization*: every `RnaResult.data` — whether it was a `list[SymbolRef]`, a single `ImportGraph`, or a `list[TestLink]` — is flattened into one uniform `RepositoryContextItem` per fact, carrying:

- `kind` (derived from which RNA method produced it)
- `payload` (the original RNA model, untouched — §6 in `02_api_spec.md`)
- `source_method` (for provenance and for Ranking's confidence-tier signal)
- a first-pass `tokens_estimate` (reusing `RnaResult.meta.tokens_estimate` where RNA already computed one; otherwise a whitespace-token estimate over the payload's serialized form)

No ranking or filtering happens here — Aggregation is pure reshaping, so it stays trivially testable with hand-built `RnaResult` fixtures and no RNA instance at all.

---

## 5. Ranking

**Class:** `ranker.Ranker`
**Input:** `list[RepositoryContextItem]`
**Output:** the same list, each item's `relevance` field set, sorted descending

A deterministic scoring function — no ML model, no LLM, reproducible given the same inputs:

```text
score(item) =
      w_hint      * hint_match(item, request.file_hints, request.symbol_hints)
    + w_confidence * confidence_tier_weight(item)      # RNA meta.confidence: precise > heuristic
    + w_recency    * recency(item)                      # git_analyzer-derived signal, when available
    + w_relation    * relation_strength(item)             # e.g. TestLink.confidence, CallEdge directness
    - w_distance     * scope_distance(item, request)       # farther from the hinted scope, lower score
```

| Weight | Default | Rationale |
|---|---|---|
| `w_hint` | 0.40 | An explicitly hinted file/symbol is almost always the most relevant fact |
| `w_confidence` | 0.20 | Prefer RNA answers backed by an LSP/whole-program tier over a tree-sitter heuristic |
| `w_recency` | 0.15 | Recently touched code is more likely relevant to an in-flight task |
| `w_relation` | 0.15 | A direct-import test link outranks a naming-convention guess |
| `w_distance` | 0.10 (penalty) | Keeps unrelated, distant facts from crowding out the requested scope |

Conversation items are ranked separately from repository items (they compete for a different, reserved slice of the budget — §6) using a simpler formula: `decision > recent_message > relevant_history_hit > summary`, with recency as the tiebreaker within each tier.

Weights live in `ContextConfig` (not hardcoded), so a deployment can retune without touching pipeline code — same posture as RNA's tunable limits.

---

## 6. Compression

**Class:** `compressor.Compressor`
**Input:** ranked `list[RepositoryContextItem]` + ranked conversation items
**Output:** the same, trimmed to fit the budget

Budget split, from `ContextConfig.max_context_tokens` (default 8,000):

```text
conversation_budget = max_context_tokens * conversation_reserve_ratio     # default 2,000
repository_budget    = max_context_tokens - conversation_budget            # default 6,000
```

Repository side, greedy over the ranked list:

1. Include items in rank order while `running_tokens <= repository_budget` **and** `count(kind == "file") <= max_files`.
2. For a `file` item whose content exceeds `max_lines_per_file` (200 by default), truncate the content *before* considering dropping the item entirely — a partial file is still more useful than no file, mirroring `rna.get_file`'s own per-file cap.
3. Once budget is exhausted, every remaining item is dropped, and one `provenance` entry is recorded per drop: `"get_callers: dropped (budget) - 4 lowest-ranked call_edge items"`.

Conversation side, in a fixed priority order regardless of rank score — because conversational continuity has a different shape than repository relevance:

1. `recent_messages` — always kept up to a floor (last 4 turns), even if this exceeds a strict pro-rata share of `conversation_budget`. Losing immediate context ("what did the user just ask") is worse than losing anything else.
2. `decisions` — kept in full unless they alone would exceed the remaining budget (rare; decisions are short statements by construction, see `04_conversation_memory.md` §3).
3. `summary` — kept if room remains.
4. `relevant_history` — truncated first, dropped entirely if none of the above leaves room.

`meta.truncated=True` is set whenever *anything* was dropped or shortened, on either side — never silently.

---

## 7. Validation

**Class:** `validator.Validator`
**Input:** compressed items + the original `ContextRequest`
**Output:** either a built `ContextPackage`, or (only for an invariant violation) a raised `ContextSecurityError`

Checks, in order:

1. **Scope boundary** — every item's originating path/session belongs to the requesting session's own repository and session id. A cross-session leak (Conversation Manager instance misconfiguration, or a cache key collision) is the one condition that raises rather than degrades (`06_contract_and_safety.md` §1).
2. **Contract completeness** — per `requesting_agent`, a minimal set of item kinds is expected (e.g. `verifier` should end up with at least one `test_link` or `file` reflecting changed files). A missing expectation is **not** an exception — it is appended to `provenance` (`"verifier contract: no test_link items found for changed files"`) so the calling agent can decide how to proceed, consistent with "never throw for a soft miss."
3. **Budget compliance** — `tokens_estimate <= token_budget` after Compression, as a final assertion-style safety net (Compression should already guarantee this; Validation exists to catch a Compression bug loudly in tests rather than silently ship an over-budget package to a model call).

Only after Validation passes does `context_manager.cache()` persist the result (§8) and `resolve()` return it.

---

## 8. Package Cache

**Class:** `cache.PackageCache` (thin wrapper)

Composes `rna.cache.store.CacheStore` directly rather than reimplementing an L1/L2 cache: same `CacheStore(cache_dir, l1_size=..., enabled=...)` constructor, same `get_or_compute`/`invalidate_subject`/`invalidate_all` methods, pointed at `<repo>/.context_cache/packages/` instead of `<repo>/.rna_cache/`. This is a direct instance of **Reuse Over Reinvention** — the compute-once-under-lock semantics, the L1 LRU, and the blob-vs-inline storage split were already built, tested, and battle-tested by RNA; the Context Manager's cache has the exact same shape of problem (small values inline, large values as blobs, per-key locking) and gets it for free.

Storage layout (parallel to `.rna_cache/`, see `04_conversation_memory.md` §5 for the Conversation Manager's own layout):

```text
<repo_root>/.context_cache/
  packages/
    manifest.sqlite     # cache key -> {inline value | blob ref, written_at}
    blobs/
      <sha256>.json        # large ContextPackage payloads
```
