# Context Subsystem — Implementation Plan

This plan turns `01_architecture.md` through `06_contract_and_safety.md` into an ordered, buildable sequence. Every phase names exactly which design-doc section it implements, so nothing here is invented at build time — implementation is the last step, not the first (per the repository's own engineering principles).

Scope is identical to the design set: `src/context/` only. No orchestrator, no agent classes, no chat-model port implementation — those are consumers/dependencies this plan wires *against* (via a narrow seam, §0.3) but does not build.

---

## 0. Preconditions

### 0.1 What already exists and will be reused, not rebuilt

| Dependency | Location | Used for |
|---|---|---|
| `RnaPort`, `Rna`, `FakeRna` | `src/rna/__init__.py`, `src/rna/facade.py`, `src/rna/fake.py` | Context Manager's only retrieval backend (`03_context_composition.md` §3) |
| `CacheStore`, `make_cache_key`, `CacheKey` | `src/rna/cache/store.py`, `src/rna/cache/keys.py` | Package cache, composed not reimplemented (`03_context_composition.md` §8, `06_contract_and_safety.md` §2) |
| `repo_fingerprint`, `content_hash` | `src/rna/repo_analyzer/fingerprint.py` | Cache key staleness component (`03_context_composition.md` §1) |
| `timed_call` observability pattern | `src/rna/observability.py` | Structured log record shape (`06_contract_and_safety.md` §3) |
| `TaskComplexity` enum values `{SIMPLE, MEDIUM, COMPLEX}` | `docs/02_specs.md` §6 | `ContextRequest.task_complexity` (`02_api_spec.md` §2) |
| Pydantic `BaseModel` config pattern | `src/rna/config.py` | `ContextConfig` shape (`02_api_spec.md` §9) |

### 0.2 What does not exist yet, and how this plan avoids blocking on it

The system-wide **chat-model port** (`docs/02_specs.md` §10) has no implementation anywhere in the repo yet (`src/reasoning/`, `src/agents/` are empty placeholder directories). `Summarizer` and the optional decision-extraction pass are the only two places in this entire subsystem that need one (`04_conversation_memory.md` §3-4).

This plan does **not** block on that port landing first, and does **not** build a permanent replacement for it. Phase 2 (§2 below) introduces one file-local, minimal `ChatModelPort` `Protocol` — `complete(messages: list[dict]) -> str` — inside `conversation/summarizer.py`, clearly marked as a **temporary seam**:

```python
class ChatModelPort(Protocol):
    """Temporary local seam. Replace with the system-wide chat-model port
    (docs/02_specs.md S10) as soon as it exists — same method shape assumed,
    this Protocol is deleted, not extended, on that day."""
    def complete(self, messages: list[dict[str, str]]) -> str: ...
```

Every deterministic/fallback path (rule-based decision extraction, naive-truncation summarization) is fully functional with **zero** `ChatModelPort` implementation available — the constructor accepts `chat_model: ChatModelPort | None = None`, and every call site already has the degrade-not-throw fallback the design docs require (`01_architecture.md` §5). This means Phase 2 ships a complete, testable Conversation Manager today, and swapping in a real chat-model implementation later is a one-line constructor change, not a design change.

### 0.3 Build order dependency graph

```text
Phase 0  Shared primitives (models, config, errors, observability)
    │
    ├─────────────────────────────┐
    ▼                             ▼
Phase 1                       Phase 2
ExecutionContext              Conversation Manager
(runtime/)                    (conversation/)
    │                             │
    └──────────────┬──────────────┘
                    ▼
                Phase 3
                Context Manager
                (manager/) -- depends on RNA (existing) + Phase 2's ConversationManagerPort
                    │
                    ▼
                Phase 4
                Fakes + contract tests
                    │
                    ▼
                Phase 5
                Integration seam (bootstrap/wiring helpers, no orchestrator)
                    │
                    ▼
                Phase 6
                Observability + safety hardening
                    │
                    ▼
                Phase 7
                Performance polish + docs sync
```

Phases 1 and 2 have no dependency on each other and can be built in either order or in parallel — this mirrors the design's own claim that Conversation Manager and ExecutionContext are independent (`01_architecture.md` §1).

---

## Phase 0 — Shared primitives

**Implements:** `02_api_spec.md` §1, §2, §5-9; `06_contract_and_safety.md` §1 (error hierarchy).
**Goal:** Every type either other component needs exists, compiles, and is importable — with zero behavior yet.

### Deliverables

```text
src/context/
  __init__.py        # re-exports: ContextManagerPort, ConversationManagerPort (defined here as
                      # Protocols), ContextResult, ContextMeta, ContextRequest, ContextPackage
  errors.py           # ContextError, ContextSecurityError, ContextConfigError
  config.py            # ContextConfig(BaseModel) -- exact fields from 02_api_spec.md S9
  models.py             # ContextMeta, ContextResult[T], ContextRequest, RepositoryContextItem,
                         # Message, Decision, ConversationSummary, ContextPackage
                         # (re-exports RepositoryContext/ConversationContext from runtime/)
  observability.py       # timed_call() context manager, mirrors src/rna/observability.py exactly
```

`ContextManagerPort` and `ConversationManagerPort` are declared in `__init__.py` (not `models.py`) because they are the subsystem's public seam, the same place `RnaPort` lives in `src/rna/__init__.py`.

### Acceptance

- `python -c "import src.context"` succeeds with no other subsystem built yet.
- `ruff check src/context` and `mypy src/context` (or project's configured type checker) pass on this phase's files alone.
- Every dataclass is `frozen=True, slots=True`, matching `src/rna/models.py`'s convention exactly — a lint/test asserts this (`tests/context/test_model_shapes.py`: iterate `models.py`'s `__dataclass_fields__`-bearing exports, assert `__dataclass_params__.frozen` and the class defines `__slots__`).
- `ContextConfig().max_context_tokens == 8000`, `.max_files == 5`, `.max_lines_per_file == 200` by default (asserts the shared-constant claim in `02_api_spec.md` §9 is actually true in code, not just in prose).

### Risks

- **Risk:** `RepositoryContext`/`ConversationContext` defined in `runtime/` before `runtime/` exists yet (Phase 1) creates a circular import between `models.py` and `runtime/`. **Mitigation:** Phase 0's `models.py` only defines `RepositoryContextItem` (not `RepositoryContext` itself) and re-exports `RepositoryContext`/`ConversationContext` via a deferred import at the bottom of `models.py`, or Phase 0 and Phase 1 are done as one atomic commit — either way, `01_architecture.md` §3.1's "one definition, never two" rule is the thing under test, not the file boundary.

---

## Phase 1 — ExecutionContext (runtime state)

**Implements:** `05_execution_context.md` in full.
**Goal:** The immutable, ownership-partitioned state container exists, with the `with_*()` functional-update API and full serialization, and is independently testable with no Context Manager, no Conversation Manager, and no RNA involved at all.

### Deliverables

```text
src/context/runtime/
  __init__.py
  request_context.py         # RequestContext
  repository_context.py       # RepositoryContext, RepositoryContextItem (canonical; models.py re-exports)
  conversation_context.py      # ConversationContext (canonical; models.py re-exports)
  planning_context.py           # PlanningContext
  execution_state.py              # ExecutionState
  verification_context.py          # VerificationContext
  metrics_context.py                # MetricsContext
  event_log.py                       # Event, EventLog (EventLog.append() returns a new EventLog)
  execution_context.py                 # ExecutionContext + with_repository/with_conversation/
                                        # with_planning/with_execution/with_verification/
                                        # with_metrics/with_event/checkpoint/to_dict
```

### Key implementation details

- Every `with_*` method: `dataclasses.replace(self, <field>=<value>, version=self.version + 1)`. No hand-rolled field copying — reuse `dataclasses.replace` so a future new field never has to be remembered in seven different `with_*` bodies.
- `EventLog.append(kind, payload) -> EventLog` returns `EventLog(events=self.events + (Event(kind, payload, at=now_iso()),))` — same immutable-append pattern as everything else in this subsystem.
- `ExecutionContext.to_dict()` — a pure recursive `dataclasses.asdict()`-equivalent walk, same helper shape as `RnaResult._to_jsonable` (`src/rna/models.py`); do not write a second JSON-shaping helper, extract and share the one that already exists if it becomes public, or duplicate the ~10-line function with a comment pointing at its RNA counterpart if extracting isn't worth a cross-subsystem import.
- `checkpoint()` returns `self` (the object *is* the checkpoint, per `05_execution_context.md` §2) — this method exists only for call-site readability at the orchestrator boundary (`ctx.checkpoint()` reads better than a bare reference at a persistence call site), not because it does anything beyond identity.

### Acceptance

- `ExecutionContext` and every sub-context are frozen dataclasses; a test asserts `with pytest.raises(FrozenInstanceError): ctx.planning = PlanningContext()`.
- `ctx.with_planning(p)` returns a **new** object (`ctx2 is not ctx`), leaves `ctx` completely unchanged, and `ctx2.version == ctx.version + 1`.
- Calling any `with_*` in a tight loop 10,000 times and checking memory/identity: no cross-contamination between versions (a regression test that mutates a `list`/`dict` passed into one version and asserts an earlier version's data didn't change — catches an accidental shallow-copy bug, since `code_changes`/`tool_results` are `tuple[dict, ...]` and the inner `dict`s are still technically mutable; document this as a known, accepted boundary rather than solving it with deep-freezing, which the design does not require).
- `to_dict()` round-trips through `json.dumps` with no custom encoder needed (i.e. no field type sneaks in that isn't JSON-native — this is what actually enforces "state is not logic," since behavior/closures can't survive a JSON round-trip).
- The reconciliation table in `05_execution_context.md` §5 is executable as a test: for every old-schema field name, assert a lookup path exists (e.g. `getattr(ctx.request, "user_query")`, `getattr(ctx.planning, "plan_steps")`, ...) — a parametrized test over the 14-row table.

### Tests

`tests/context/runtime/test_execution_context.py`, `test_ownership_immutability.py`, `test_reconciliation_table.py`.

---

## Phase 2 — Conversation Manager

**Implements:** `04_conversation_memory.md` in full; `02_api_spec.md` §4.
**Goal:** A fully working `ConversationManagerPort` implementation, backed by SQLite, with every LLM-dependent path degrading gracefully with zero chat-model implementation wired in (§0.2).

### Deliverables, in build order (each is independently testable before the next starts)

1. **`message_store.py`** — `MessageStore`: `append(message)`, `get_recent(n, roles)`, `get_by_id(id)`. SQLite schema exactly as in `04_conversation_memory.md` §1. Single-writer lock. **No dependency on anything else in this phase** — build and test first.
2. **`memory_index.py`** — `MemoryIndex`: keyword tier only in this pass (`04_conversation_memory.md` §5, table row 1 — SQLite FTS or an in-process inverted index for small sessions). The optional embedding tier is a stretch item, not a blocker (see Phase 7).
3. **`decision_extractor.py`** — `DecisionExtractor`: rule-based pass only in this pass (regex trigger phrases per `DecisionCategory`, `04_conversation_memory.md` §3 point 1). Accepts `chat_model: ChatModelPort | None = None`; if `None`, the optional pass is simply skipped (not attempted, not degraded — there was nothing to degrade from).
4. **`summarizer.py`** — `Summarizer`: defines the temporary `ChatModelPort` Protocol (§0.2). Implements the naive-truncation fallback path fully (`04_conversation_memory.md` §4) — this is the *default* behavior with `chat_model=None`, not a fallback-only-on-failure path, since there is no real implementation to fail yet. When a `chat_model` is later provided, the rolling-summary path (`old_summary + new_messages -> chat_model.complete(...)`) activates automatically; the fallback path is exercised by tests via a fake `ChatModelPort` that raises, proving the failure-degrades-gracefully behavior independently of whether a real implementation exists.
5. **`retriever.py`** — `Retriever`: combines `MessageStore` + `MemoryIndex` + decision boost + recency decay (`04_conversation_memory.md` §5). Depends on 1-2.
6. **`conversation_manager.py`** — `ConversationManager` facade implementing `ConversationManagerPort`: composes 1-5, one method per port method (`02_api_spec.md` §4). `__init__(self, session_id: str, config: ContextConfig, chat_model: ChatModelPort | None = None)`.

### Acceptance

- `ConversationManager` satisfies `ConversationManagerPort` (`isinstance(cm, ConversationManagerPort)` via `runtime_checkable` Protocol, same pattern `test_facade_contract.py` uses for `RnaPort`).
- `append()` for two different `session_id` instances never cross-contaminates: a test constructs two `ConversationManager`s pointed at the same `cache_dir` with different `session_id`s, appends to both, and asserts `get_recent()` on either never contains the other's messages — the concrete regression test for the one invariant that raises `ContextSecurityError` if ever violated (`06_contract_and_safety.md` §1). Add a second test that *forces* a session-id mismatch at the storage layer (bypassing the public API, e.g. directly manipulating the SQLite row) and asserts the read path raises `ContextSecurityError` rather than silently returning the wrong session's row — this is the actual boundary-violation test, not just a "normal usage never leaks" test.
- `summarize()` with `chat_model=None` returns a naive summary, `meta.degraded=True`, `reason` mentions no chat model was configured, and never raises.
- `summarize()` with a `chat_model` fake that raises returns the same naive fallback, `meta.degraded=True`, `reason="summarizer_unavailable"`, and never raises — proving the failure path independent of the "not configured" path (they are two different `reason` strings for two different situations).
- `get_decisions()` returns rule-based extractions for a fixture transcript containing at least one instance of every trigger phrase category.
- `clear()` default (`keep_decisions=True`) leaves the `decisions` table intact and empties `messages`/`summaries`; `clear(keep_decisions=False)` empties all three.

### Tests

`tests/context/conversation/test_message_store.py`, `test_decision_extractor.py`, `test_summarizer.py`, `test_retriever.py`, `test_conversation_manager_contract.py`, `test_session_isolation.py`.

### `FakeConversationManager`

Built at the end of this phase (not deferred to Phase 4, since Phase 3 needs it to test the Context Manager without a real SQLite-backed Conversation Manager): a scripted, in-memory dict-backed implementation of `ConversationManagerPort`, same role `FakeRna` plays for `RnaPort` (`06_contract_and_safety.md` §4). Lives at `src/context/fake.py` alongside `FakeContextManager` (added in Phase 3) so both fakes ship from one file, mirroring `src/rna/fake.py`'s single-file convention.

---

## Phase 3 — Context Manager

**Implements:** `03_context_composition.md` in full; `02_api_spec.md` §3.
**Goal:** A fully working `ContextManagerPort` implementation. This is the largest phase; each pipeline stage is built and unit-tested in isolation *before* they are wired into the `resolve()` pipeline, per `03_context_composition.md`'s own stage boundaries.

### Deliverables, in pipeline order

1. **`analyzer.py`** — `RequirementAnalyzer`: the `(requesting_agent, task_complexity) -> RetrievalPlan` rule table from `03_context_composition.md` §2, as an explicit `dict`/`match` — not scattered conditionals. `RetrievalPlan = list[tuple[str, dict]]` (method name, kwargs) plus a `query_conversation: bool` flag. Pure function, zero I/O, testable with no RNA/Conversation Manager instance at all.
2. **`retrieval_planner.py`** — `RetrievalPlanner(rna: RnaPort, conversation: ConversationManagerPort, config: ContextConfig)`: executes a `RetrievalPlan` — de-dupes `(method, kwargs)` pairs, fires the RNA batch and the Conversation Manager query concurrently (bounded pool; use `concurrent.futures.ThreadPoolExecutor` since RNA/SQLite calls are I/O-bound, not CPU-bound — no new async runtime introduced into a subsystem that has no other async requirement), applies `retrieval_timeout_ms` per call, returns `(list[RnaResult], ConversationContext)`.
3. **`aggregator.py`** — `Aggregator`: pure reshaping, `03_context_composition.md` §4. No RNA/Conversation Manager dependency — takes already-fetched results in, testable with hand-built `RnaResult` fixtures exclusively.
4. **`ranker.py`** — `Ranker`: the scoring formula and weight table from `03_context_composition.md` §5, weights sourced from `ContextConfig` (add the five `w_*` fields to `ContextConfig` in this phase — they were named in the design doc but are new config surface, so add them here where they're first consumed, not retroactively in Phase 0).
5. **`compressor.py`** — `Compressor`: the budget-split and greedy-inclusion algorithm from `03_context_composition.md` §6, including the fixed conversation-side priority order (recent > decisions > summary > relevant_history).
6. **`validator.py`** — `Validator`: the three checks from `03_context_composition.md` §7, including the one path that raises `ContextSecurityError` (cross-session/cross-scope) versus the two that append to `provenance` instead.
7. **`cache.py`** — `PackageCache`: thin wrapper instantiating `rna.cache.store.CacheStore` pointed at `<cache_dir>/packages/`, per `03_context_composition.md` §8 and `06_contract_and_safety.md` §2 — literally import and construct the existing class, do not subclass or reimplement it.
8. **`context_manager.py`** — `ContextManager` facade implementing `ContextManagerPort`: wires 1-7 into `resolve()`, `expand()`, `refresh()`, `invalidate()`, `cache()`, `compose()` exactly per `02_api_spec.md` §3. `__init__(self, rna: RnaPort, conversation: ConversationManagerPort, config: ContextConfig)`.

### Implementation notes specific to this phase

- `compose()` is implemented first among the six port methods (it is stages 5-7 of the pipeline with no retrieval), and `resolve()`/`expand()` are implemented as thin wrappers that call retrieval then delegate to `compose()` — this is the design's own explicit instruction (`02_api_spec.md` §3.6: "`resolve()` is implemented as *retrieve, then delegate to `compose()`*"), not an optional refactor.
- `expand()`'s content-hash re-validation (`02_api_spec.md` §3.2) reuses RNA's own `content_hash`/`repo_fingerprint` functions per item's `source_method`/path, exactly like the cache-key construction in `03_context_composition.md` §1 — one fingerprinting mechanism used everywhere in this subsystem, never two.
- `refresh()` is the simplest of the six: `invalidate(scope_of(package.request))` then `resolve(package.request)`. Implement it last, as a two-line composition of already-built methods, to keep it honest that it adds no new logic of its own.

### Acceptance

- `ContextManager` satisfies `ContextManagerPort` (contract test, mirrors `test_facade_contract.py`).
- **Golden-table test** for `RequirementAnalyzer`: every row of the table in `03_context_composition.md` §2 has an exact expected `RetrievalPlan`, asserted verbatim — a change to retrieval strategy is a visible diff in this one test file, never a silent behavior change.
- **Determinism test** for `Ranker`/`Compressor`: the same fixture input, run twice, produces byte-identical output ordering and drop decisions.
- **Budget compliance test**: a fixture that deliberately exceeds `max_files`/`max_lines_per_file`/`max_context_tokens` individually (three separate test cases, not one combined one) and asserts the correct dimension triggered truncation, with the correct `provenance` entry.
- **End-to-end pipeline test** using `FakeRna` (existing, `src/rna/fake.py`) + `FakeConversationManager` (Phase 2) + a real `ContextManager`: `resolve()` on a scripted fixture returns a `ContextPackage` matching an expected golden snapshot, with zero real filesystem/SQLite/subprocess activity.
- `invalidate()` and the package cache round-trip: `resolve()` twice with no intervening change hits the cache the second time (`meta.cache_hit=True`, and the golden test asserts the second call issued **zero** RNA/Conversation Manager calls — instrument the fakes with call counters for this specific assertion).

### Tests

`tests/context/manager/test_analyzer.py`, `test_retrieval_planner.py`, `test_aggregator.py`, `test_ranker.py`, `test_compressor.py`, `test_validator.py`, `test_cache.py`, `test_context_manager_contract.py`, `test_resolve_pipeline_e2e.py`.

---

## Phase 4 — Fakes & cross-cutting contract tests

**Implements:** `06_contract_and_safety.md` §4.
**Goal:** Close the loop the design promised: both ports have a fake that Agent Layer development can depend on today, and the parametrized "real vs fake, same shape" contract test pattern RNA already established is applied here too.

### Deliverables

- `src/context/fake.py` — `FakeContextManager` (scripted `ContextPackage` responses keyed by a caller-supplied predicate or literal `ContextRequest` match, same spirit as `FakeRna`'s scripted dicts) alongside the `FakeConversationManager` already built in Phase 2.
- `tests/context/conftest.py` — shared fixtures: `fake_rna`, `conversation_manager` (real, tmp-dir-backed), `fake_conversation_manager`, `context_manager` (real, wired to `fake_rna` + real `conversation_manager`), `fake_context_manager` — mirrors `tests/rna/conftest.py`'s fixture-naming convention exactly.
- `tests/context/test_port_contracts.py` — the parametrized `["real", "fake"]` shape test for both ports, mirroring `test_facade_contract.py` line for line in structure.

### Acceptance

- Every test written in Phases 1-3 that used an ad hoc fixture is not touched (no regression); this phase only adds the shared fixture file and the cross-cutting contract tests, so it should be a strictly additive diff.
- A one-line smoke test proves an Agent-Layer-shaped test (a stand-in function that takes `ContextManagerPort` and `ConversationManagerPort` as parameters) runs successfully against the fakes with zero repository, zero RNA instance, zero SQLite file created.

---

## Phase 5 — Integration seam

**Implements:** the consumption contract described in `06_contract_and_safety.md` §1, **without** building the Agent Layer itself (explicitly out of scope, per the original design brief).

### Deliverables

- `src/context/bootstrap.py` (new, small) — one factory function: `build_context_subsystem(rna: RnaPort, session_id: str, config: ContextConfig | None = None) -> tuple[ContextManagerPort, ConversationManagerPort]`. This is the *only* place in the codebase, once the orchestrator exists, that will construct these two concrete classes — everything downstream receives them as already-typed `Protocol` parameters. Building this now, ahead of the orchestrator, means the orchestrator's eventual wiring code is a single import + one function call, not a rediscovery of constructor arguments.
- A short usage note added to `src/context/README.md`'s quick start (already present) confirming `bootstrap.build_context_subsystem` is the recommended construction path over calling `ContextManager(...)`/`ConversationManager(...)` directly — keeps exactly one canonical construction path.

### Acceptance

- `build_context_subsystem` returns objects that pass the Phase 4 contract tests when substituted in.
- No new dependency on anything under `src/orchestrator/`, `src/agents/`, or `src/reasoning/` is introduced — a grep-based test (`tests/context/test_no_forward_dependencies.py`) asserts `src/context/` never imports from those packages, keeping the one-way dependency graph in `01_architecture.md` §2 true at import-time, not just in prose.

---

## Phase 6 — Observability & safety hardening

**Implements:** `06_contract_and_safety.md` §1, §3.

### Deliverables

- Wrap every `ContextManagerPort`/`ConversationManagerPort` method body in the `timed_call` pattern from `observability.py` (Phase 0), emitting the exact structured record shown in `06_contract_and_safety.md` §3, including `llm_invoked` on `Summarizer`/`DecisionExtractor` call paths.
- A dedicated `tests/context/test_security_invariants.py` consolidating every "must raise `ContextSecurityError`" case from earlier phases into one file, so the full safety surface is auditable by reading one test module, not scattered across seven.

### Acceptance

- Every log record in a captured test run is valid JSON and contains every field the doc specifies — a schema-shape test, not a byte-for-byte snapshot (log content will legitimately vary run to run; shape must not).

---

## Phase 7 — Performance polish & stretch scope

**Implements:** the parts of `03_context_composition.md`/`04_conversation_memory.md` explicitly marked optional/opt-in in the design.

### Deliverables (each independently shippable, none blocking the phases above)

- Optional embedding tier for `MemoryIndex` (`memory_embedding_model="sentence-transformers"`) — additive, same feature-flag shape as RNA's own `rna-embeddings` extra in `pyproject.toml`; add a matching `context-embeddings` optional-dependency group rather than folding it into the base `dependencies` list.
- Chat-model-assisted decision extraction pass, once a real `ChatModelPort`-shaped implementation exists anywhere in the codebase (§0.2) — wire it in via the existing constructor parameter; no interface change needed.
- Performance budget table for this subsystem's own methods (`resolve` cold/warm, `append`, `summarize`), mirroring RNA's `04_indexing_and_caching.md` §4 — write it once real numbers exist from a benchmark fixture, not as a guess up front.
- Package-cache warm-up helper (`context_manager.warm()`?) — only if profiling of a real Agent Layer integration shows cold-cache `resolve()` latency actually matters in practice; do not build speculatively.

---

## Milestones

### M1 — Data layer complete (end of Phase 1)
`ExecutionContext` and every sub-context exist, are immutable, serialize cleanly, and the reconciliation table is proven by a passing test. Nothing computes anything yet.

### M2 — Memory complete (end of Phase 2)
A real session can append messages, get a summary (naive or LLM-backed), retrieve relevant history, and extract decisions — entirely independent of RNA and of the Context Manager.

### M3 — Composition complete (end of Phase 4)
`ContextManager.resolve()` works end-to-end against `FakeRna` + a real `ConversationManager`, respects every budget, caches correctly, and both ports have fakes ready for Agent Layer development to depend on.

### M4 — Integration-ready (end of Phase 6)
`bootstrap.build_context_subsystem()` is the one call an orchestrator needs; every safety invariant has a dedicated, passing test; every call is observable via structured logs. The Context Subsystem is a complete, independently-shippable unit that the Agent Layer (when built) consumes without needing to understand its internals — exactly the encapsulation goal stated in `docs/README.md` §1.

---

## Anti-goals (for this implementation, specifically)

- No orchestrator, FSM, agent class, or tool layer is built as part of this plan — those consume this subsystem's ports and are separate work, explicitly out of scope per the original design brief.
- No permanent chat-model port implementation is built here — only the minimal, clearly-temporary local seam (§0.2) needed to make `Summarizer`/`DecisionExtractor` honest about their one real dependency without inventing a second, competing LLM integration for the codebase to eventually reconcile.
- No speculative embedding/ML ranking is added to `Ranker` — it stays a deterministic formula per `03_context_composition.md` §5 unless a future design revision explicitly changes that.
- No new cache implementation — `PackageCache` composes `rna.cache.store.CacheStore`; if that class ever needs a capability it doesn't have, the fix is to extend RNA's cache (a cross-cutting improvement both subsystems benefit from), not to fork a second cache implementation inside `src/context/`.
