# Context Subsystem — Architecture

## 1. Component relationship

The three components are not peers with equal standing. Two are services (`Protocol`-based ports, exactly like `RnaPort`); one is a data container with no behavior. Their relationship is hierarchical, not flat:

```text
                     Context Subsystem
                            │
            ┌───────────────┴───────────────┐
            │                               │
            ▼                               ▼
     Context Manager                Conversation Manager
            │
            ▼
     ExecutionContext
```

- **Conversation Manager** owns conversational memory. It has no dependency on Context Manager, RNA, or ExecutionContext — it is queried, not orchestrated.
- **Context Manager** owns composition and retrieval orchestration. It depends on RNA (repository facts) and on Conversation Manager (conversational facts), merges both, and is the only component that **writes** the `repository` and `conversation` slices of an `ExecutionContext`.
- **ExecutionContext** owns nothing. It is the runtime state container every other component (Planner, Context Manager, Executor, Verifier) reads from and writes exactly one slice of.

Each component has exactly one reason to change (`README.md` §4): Conversation Manager changes when long-term memory improves, Context Manager changes when retrieval/ranking/compression improves, ExecutionContext changes when the runtime itself needs to track new state.

---

## 2. Dependency graph

```text
Execution Planner   Executor   Verifier   Reviewer
        │               │          │          │
        └───────────────┴────┬─────┴──────────┘
                              │  (ContextRequest in, ContextPackage out)
                              ▼
                      Context Manager
                       │            │
                       ▼            ▼
                     RNA      Conversation Manager
                       │
                       ▼
                  Repository (via RNA's own engines)

ExecutionContext
        ▲
        │  (each stage writes exactly one sub-context, via with_*())
        │
Planner · Context Manager · Executor · Verifier · Reviewer
```

Two invariants fall out of this graph and are enforced by *not exposing any other entry point*:

1. **The Planner never touches RNA. The Executor never touches RNA. The Verifier never touches RNA.** Every one of them talks to `Context Manager`. RNA's own README describes it as "called by coding agents … exactly when they need one fact" — that remains true, except in this system the one caller that ever holds an `Rna`/`RnaPort` reference is the Context Manager. This is a deliberate, additional constraint this system places on top of RNA (which itself is agent-agnostic and does not care who calls it) — see `06_contract_and_safety.md` §1 for why.
2. **Nobody but the Context Manager writes `RepositoryContext` or `ConversationContext` into an `ExecutionContext`.** Planning writes `PlanningContext`. Execution writes `ExecutionState`. Verification writes `VerificationContext`. Metrics is updated by whichever stage just ran. Nobody owns everything (`05_execution_context.md` §3).

---

## 3. Package layout

```text
context/
  __init__.py                 # ContextManagerPort, ConversationManagerPort protocols; facade exports
  config.py                    # ContextConfig
  errors.py                     # ContextError, ContextSecurityError, ContextConfigError
  models.py                      # ContextResult, ContextMeta, ContextRequest, ContextPackage,
                                  # RepositoryContextItem, Message, Decision, ConversationSummary
                                  # (RepositoryContext / ConversationContext are defined once, in
                                  #  runtime/, and re-exported here — see §3.1)
  observability.py                 # timed_call(), structured log record (mirrors rna/observability.py)

  # test doubles: tests/doubles/context.py (FakeContextManager, FakeConversationManager)

  manager/
    __init__.py
    context_manager.py               # ContextManager: resolve / expand / refresh / invalidate / cache / compose
    analyzer.py                       # RequirementAnalyzer: ContextRequest -> RetrievalPlan (deterministic rules)
    retrieval_planner.py               # RetrievalPlanner: RetrievalPlan -> batched rna.* calls, timeouts, limits
    aggregator.py                       # Aggregator: RnaResult(s) + ConversationContext -> RepositoryContextItem list
    ranker.py                            # Ranker: deterministic relevance scoring
    compressor.py                         # Compressor: token/file/line budget enforcement
    validator.py                           # Validator: invariant checks -> ContextPackage
    cache.py                                 # ContextPackage cache (composes rna.cache.store.CacheStore)

  conversation/
    __init__.py
    conversation_manager.py            # ConversationManager: append / summarize / retrieve / get_decisions / get_recent / clear
    message_store.py                    # Append-only message log (SQLite)
    summarizer.py                        # Rolling summarization via the existing chat-model port
    decision_extractor.py                 # Rule-based (+ optional chat-model-assisted) decision extraction
    memory_index.py                        # Keyword index (always) + optional embedding index
    retriever.py                            # Ranked retrieval over message_store + memory_index

  runtime/
    __init__.py
    execution_context.py               # ExecutionContext: the container + with_*() functional-update API
    request_context.py                  # RequestContext
    repository_context.py                # RepositoryContext, RepositoryContextItem (canonical definition)
    conversation_context.py               # ConversationContext (canonical definition)
    planning_context.py                    # PlanningContext
    execution_state.py                      # ExecutionState
    verification_context.py                  # VerificationContext
    metrics_context.py                        # MetricsContext
    event_log.py                               # Event, EventLog

  docs/                                        # this design set
    README.md
    01_architecture.md
    02_api_spec.md
    03_context_composition.md
    04_conversation_memory.md
    05_execution_context.md
    06_contract_and_safety.md

  tests/
```

This supersedes the empty `src/context_manager/` placeholder package — the subsystem is a peer of `src/rna/` at the top of `src/`, not a submodule of anything else, since both are infrastructure the Agent Layer depends on, not the other way around.

### 3.1 One definition per type, never two

`RepositoryContext` and `ConversationContext` are both (a) the return shape of a Context Manager query, and (b) two of the eight sub-contexts inside `ExecutionContext`. Rather than defining them twice — once for the "API contract" and once for the "runtime state" — they are defined exactly once, in `runtime/repository_context.py` and `runtime/conversation_context.py`, and `models.py` re-exports them. There is exactly one `RepositoryContext` type in this codebase. This avoids the "similar helper functions, competing abstractions" drift the engineering rules explicitly call out.

---

## 4. Request lifecycle (example)

`planner.py` calling `context_manager.resolve(...)` while working on "add caching to `pkg/parser.py`":

```text
 1. Planner calls:
      context_manager.resolve(ContextRequest(
          task_description="add caching to pkg/parser.py",
          task_complexity="MEDIUM",
          requesting_agent="planner",
          file_hints=("pkg/parser.py",),
      ))

 2. ContextManager computes a cache key from
      (repo_fingerprint, conversation_state_hash, request_fingerprint)
      - HIT  -> return cached ContextPackage immediately (no RNA calls, no conversation query)
      - MISS -> continue

 3. RequirementAnalyzer maps (task_complexity=MEDIUM, requesting_agent=planner, file_hints)
    to a RetrievalPlan via a deterministic rule table (03_context_composition.md S2):
      get_file(pkg/parser.py)
      get_symbol(...) / get_callers(...) for symbols named in file_hints
      get_import_graph(scope=pkg)
      get_tests(pkg/parser.py)

 4. RetrievalPlanner fires two independent batches concurrently (bounded worker pool):
      (a) every planned rna.* call, against the injected RnaPort
      (b) conversation_manager.retrieve(query=task_description)
              + get_recent() + get_decisions()
    Neither batch depends on the other's output -- only Aggregation (step 5) needs both.

 5. Aggregator flattens every RnaResult.data plus the ConversationContext into a list of
    RepositoryContextItem (kind, payload, source_method) -- one shape, regardless of which
    rna.* method or which conversation call produced it.

 6. Ranker scores every item (hint match, RNA confidence tier, recency, relation strength)
    and sorts descending.

 7. Compressor enforces the budget: max_context_tokens (default 8000), max_files (default 5),
    max_lines_per_file (default 200) -- truncating file content before dropping whole items,
    dropping lowest-ranked items first, never raising.

 8. Validator checks invariants: nothing escaped the requesting session's scope, the "planner"
    contract's required item kinds are present (or the gap is recorded in provenance),
    total tokens_estimate <= budget.

 9. ContextPackage is built and wrapped in ContextResult with meta.cost_ms, meta.cache_hit=False,
    meta.truncated, meta.sources=("rna", "conversation").

10. cache() stores the ContextPackage under the key computed in step 2.

11. Returned to the Planner, which folds it into the run's ExecutionContext:
      ctx = ctx.with_repository(package.repository).with_conversation(package.conversation)
```

Subsequent steps in the *same* run that ask for an overlapping scope hit the cache in step 2; a step that only needs one more file calls `expand()` instead of `resolve()`, which reuses every already-validated item and only issues the delta retrieval (`02_api_spec.md` §3.2).

---

## 5. Degradation policy

Same rule RNA already committed to, applied to this subsystem: **never throw because a nice-to-have signal is missing; only throw because a boundary was violated.**

| Situation | Behavior |
|---|---|
| One planned RNA call fails or times out | Skip that item only; `meta.degraded=True`, `meta.reason` names the failed method; every other item is still returned |
| RNA facade entirely unreachable / misconfigured | `RepositoryContext` is empty, `degraded=True`, `reason="rna_unavailable"`; `ConversationContext` is still returned — the package is conversation-only, not an exception |
| Conversation store empty (new session, cold start) | `ConversationContext` is empty; this is an expected state, not a degradation |
| Combined item set exceeds the token/file/line budget | Compressor truncates/drops lowest-ranked items; `meta.truncated=True`; never raises |
| Summarizer's chat-model call fails | `summarize()` falls back to a naive last-N-messages join; `meta.degraded=True`, `reason="summarizer_unavailable"` |
| Decision extractor's chat-model call fails | Falls back to the rule-based extraction pass only; `meta.degraded=True`, `reason="extractor_llm_unavailable"` |
| `expand()`/`refresh()` called against a stale cached package (repo changed underneath it) | `refresh()` recomputes fully; `expand()` re-validates every cached item's content hash and drops any that changed, `degraded=True`, `reason="stale_items_dropped"` |
| A request's `file_hints`/scope would read outside the requesting session's own repository/session boundary | Raises `ContextSecurityError` immediately — this **is** an invariant violation (`06_contract_and_safety.md` §1) |

---

## 6. Concurrency model

- `ContextManager.resolve()` is safe to call concurrently (e.g. a Planner pre-fetching context for two candidate plan branches at once). The package cache uses the same compute-once-under-lock pattern as `rna.cache.store.CacheStore` — reused directly, not reimplemented (`06_contract_and_safety.md` §2) — so concurrent callers requesting the same package await one computation, not two.
- Within a single `resolve()`, the RNA retrieval batch and the Conversation Manager query run concurrently against a bounded worker pool, since neither depends on the other's output (§4, step 4).
- `ConversationManager.append()` is single-writer: message ordering is a correctness requirement (summaries and decisions are computed over an ordered log), so appends take a lock around the message store. `retrieve()`, `get_recent()`, and `get_decisions()` are read-only against a consistent snapshot and never block on that lock beyond a single row read.
- `ExecutionContext` is immutable per version. The orchestrator holds exactly one live reference and reassigns it (`ctx = ctx.with_planning(...)`); every concurrent reader (a TUI status projection, a logger, a checkpoint writer) always observes a fully-formed, internally consistent snapshot — never a partially updated object, and never needs a lock to read it.
