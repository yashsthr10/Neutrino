# Context Subsystem — composition, conversation memory, and runtime state

Host-side infrastructure that decides **what an agent gets to see** on each step. It sits between RNA (repository facts) and the Agent Layer (Planner / Coder / Verifier / Reviewer). It never plans, never writes code, and never calls RNA from outside this package — agents talk only to Context Manager.

```text
Context Subsystem
├── Context Manager        — composition + retrieval orchestration (the only caller of RNA)
├── Conversation Manager   — conversational memory (messages, summaries, decisions)
└── ExecutionContext       — runtime state container (not a service)
```

- **Library:** `from src.context import ContextManager, ConversationManager, ExecutionContext, build_context_subsystem`
- **Fakes (tests):** `FakeContextManager`, `FakeConversationManager`
- Deeper design docs live in [`docs/`](docs/).

Unlike RNA, this subsystem is **not** exposed as MCP tools or model-callable functions. It runs *before* a model call to build that call's input.

---

## Install

From the NeutrinoCLI repo root (same as RNA — no extra package yet):

```bash
pip install -e .
```

Verify:

```bash
python -c "from src.context import build_context_subsystem; print('ok')"
```

---

## Quick start (library)

Prefer `build_context_subsystem(...)` — the canonical wiring path:

```python
from pathlib import Path
from src.rna import Rna, RnaConfig
from src.context import (
    ContextConfig,
    ContextRequest,
    Message,
    build_context_subsystem,
)

repo = Path("/path/to/your/repo").resolve()
rna = Rna(RnaConfig(repo_path=repo))

cm, conversation = build_context_subsystem(
    rna,
    session_id="session-123",
    config=ContextConfig(),
    repo_path=repo,
)

conversation.append(
    Message(role="user", content="add caching to pkg/parser.py", created_at="2026-01-01T00:00:00Z")
)

result = cm.resolve(
    ContextRequest(
        task_description="add caching to pkg/parser.py",
        task_complexity="MEDIUM",
        requesting_agent="planner",
        file_hints=("pkg/parser.py",),
        symbol_hints=("parse_request",),
    )
)

print(result.data.repository.items)       # tuple[RepositoryContextItem, ...]
print(result.data.conversation.summary)    # ConversationSummary | None
print(result.meta.truncated, result.meta.degraded, result.meta.sources)
```

With config:

```python
cfg = ContextConfig(
    cache_dir=repo / ".context_cache",
    max_context_tokens=8_000,
    max_files=5,
    max_lines_per_file=200,
    conversation_reserve_ratio=0.25,
    cache_enabled=True,
)
cm, conversation = build_context_subsystem(rna, "session-123", cfg, repo_path=repo)
```

---

## Common return shape

Every method that can degrade or partially fail returns `ContextResult[T]`:

| Field | Type | Meaning |
|---|---|---|
| `data` | `T` | Method-specific payload |
| `meta.cost_ms` | `float` | Wall time for the call |
| `meta.cache_hit` | `bool` | Served from the package/conversation cache |
| `meta.truncated` | `bool` | Budget cap applied (files, lines, tokens, message count) |
| `meta.degraded` | `bool` | A pipeline component fell back (RNA unreachable, summarizer LLM failed, …) |
| `meta.reason` | `str \| None` | Why degraded / extra context |
| `meta.error` | `str \| None` | Soft error (not an exception) |
| `meta.tokens_estimate` | `int` | Rough size hint for budget accounting |
| `meta.sources` | `tuple[str, ...]` | Which of `{"rna", "conversation", "cache"}` contributed |

```python
result.to_dict()  # JSON-serializable {"data": ..., "meta": {...}}
```

**Exceptions (rare):** `ContextSecurityError` for a cross-session / cross-scope boundary violation. Soft misses use `meta` — see [`docs/01_architecture.md`](docs/01_architecture.md) §5.

---

## Method index

### Context Manager

| Method | One-line purpose |
|---|---|
| [`resolve`](#1-resolve) | Full pipeline: request in, bounded `ContextPackage` out |
| [`expand`](#2-expand) | Widen an existing package with a delta request |
| [`refresh`](#3-refresh) | Recompute a package after repo/conversation changed |
| [`invalidate`](#4-invalidate) | Clear the package cache for one scope or everything |
| [`cache`](#5-cache) | Persist a package built via `compose()` |
| [`compose`](#6-compose) | Merge-only: skip retrieval, still rank/compress/validate |

### Conversation Manager

| Method | One-line purpose |
|---|---|
| [`append`](#7-append) | Store one message; triggers decision extraction + conditional summarization |
| [`summarize`](#8-summarize) | Return the current rolling summary |
| [`retrieve`](#9-retrieve) | Keyword/meaning search over this session's history |
| [`get_decisions`](#10-get_decisions) | Architecture / preference / plan / constraint statements |
| [`get_recent`](#11-get_recent) | Last N messages, optionally filtered by role |
| [`clear`](#12-clear) | Reset session history (decisions survive by default) |

### ExecutionContext

| Method | One-line purpose |
|---|---|
| [`with_*`](#13-executioncontext) | Immutable functional updates (`with_planning`, `with_repository`, …) |
| [`checkpoint`](#13-executioncontext) | Identity helper for persistence call sites |
| [`to_dict`](#13-executioncontext) | JSON-serializable snapshot |

Helpers: [`build_context_subsystem`](#helpers).

---

## 1. `resolve`

Primary entry point. Runs the full pipeline: Requirement Analysis → Retrieval Planning → RNA + Conversation Manager → Aggregation → Ranking → Compression → Validation → `ContextPackage`.

### Signature

```python
resolve(request: ContextRequest) -> ContextResult[ContextPackage]
```

### Input

| Param | Required | Description |
|---|---|---|
| `request` | yes | A [`ContextRequest`](#contextrequest) |

### Output (`data`: `ContextPackage`)

| Field | Type | Description |
|---|---|---|
| `request` | `ContextRequest` | Echo of the input request |
| `repository` | `RepositoryContext` | Ranked, budgeted repository facts |
| `conversation` | `ConversationContext` | Recent messages, summary, decisions, relevant history |
| `tokens_estimate` | `int` | Total estimated tokens in the package |
| `token_budget` | `int` | Budget used for this resolve |
| `truncated` | `bool` | True if anything was dropped or shortened |
| `provenance` | `tuple[str, ...]` | Human-readable include/drop reasons |
| `created_at` | `str` | ISO-8601 timestamp |
| `cache_key` | `str` | Key used for package caching |

Second call with the same request + unchanged repo/conversation → `meta.cache_hit=True` (no RNA calls).

### Usage

```python
r = cm.resolve(
    ContextRequest(
        task_description="add caching to pkg/parser.py",
        task_complexity="MEDIUM",
        requesting_agent="planner",
        file_hints=("pkg/parser.py",),
        symbol_hints=("parse_request",),
    )
)
for item in r.data.repository.items:
    print(item.kind, item.relevance, item.source_method)
print(r.data.provenance)
```

---

## 2. `expand`

Widen an already-resolved package without a full recompute — “everything from before, plus one more file/symbol.”

### Signature

```python
expand(package: ContextPackage, *, additional: ContextRequest) -> ContextResult[ContextPackage]
```

### Input

| Param | Required | Description |
|---|---|---|
| `package` | yes | Previously resolved `ContextPackage` |
| `additional` | yes | Delta `ContextRequest` (only what is newly needed) |

Existing items are kept; only the delta triggers new retrieval. Compressor re-runs if the union exceeds budget.

### Output (`data`: `ContextPackage`)

Same shape as [`resolve`](#1-resolve).

### Usage

```python
base = cm.resolve(ContextRequest(
    task_description="edit parser",
    task_complexity="MEDIUM",
    requesting_agent="coder",
    file_hints=("pkg/parser.py",),
))
wider = cm.expand(
    base.data,
    additional=ContextRequest(
        task_description="also need router callers",
        task_complexity="MEDIUM",
        requesting_agent="coder",
        file_hints=("pkg/router.py",),
        symbol_hints=("handle",),
    ),
)
print(len(wider.data.repository.items))
```

---

## 3. `refresh`

Recompute a package because the underlying repository or conversation changed (e.g. Executor applied a patch to a file already in context).

### Signature

```python
refresh(package: ContextPackage) -> ContextResult[ContextPackage]
```

### Input

| Param | Required | Description |
|---|---|---|
| `package` | yes | Package to refresh (its stored `request` is replayed) |

Equivalent to `invalidate(...)` then `resolve(package.request)`.

### Usage

```python
fresh = cm.refresh(stale_package)
print(fresh.meta.cache_hit)  # False — recomputed
```

---

## 4. `invalidate`

Clear the package cache for one scope or entirely. Does **not** clear RNA's own `.rna_cache`.

### Signature

```python
invalidate(scope: str | None = None) -> None
```

### Input

| Param | Required | Description |
|---|---|---|
| `scope` | no | Hint path (currently triggers full package-cache clear); `None` = everything |

### Usage

```python
cm.invalidate("pkg/parser.py")
cm.invalidate()  # all
```

---

## 5. `cache`

Explicitly persist a package built via `compose()` (bypassing `resolve()`'s automatic caching) — useful when reassembling from a checkpointed `ExecutionContext`.

### Signature

```python
cache(package: ContextPackage) -> None
```

### Usage

```python
composed = cm.compose(repository=repo_ctx, conversation=conv_ctx)
cm.cache(composed.data)
```

---

## 6. `compose`

Merge-only entry point: given already-fetched slices, run Ranking → Compression → Validation. Does **not** call RNA or Conversation Manager. `resolve()` is implemented as *retrieve, then delegate to `compose()`*.

### Signature

```python
compose(
    *,
    repository: RepositoryContext | None = None,
    conversation: ConversationContext | None = None,
    budget: int | None = None,
) -> ContextResult[ContextPackage]
```

### Input

| Param | Required | Description |
|---|---|---|
| `repository` | no | Pre-built repository slice |
| `conversation` | no | Pre-built conversation slice |
| `budget` | no | Override `max_context_tokens` for this compose |

### Usage

```python
from src.context import RepositoryContext, ConversationContext

r = cm.compose(
    repository=RepositoryContext(items=(), tokens_estimate=0, truncated=False),
    conversation=ConversationContext(
        recent_messages=(),
        summary=None,
        relevant_history=(),
        decisions=(),
        tokens_estimate=0,
        truncated=False,
    ),
    budget=4_000,
)
print(r.data.tokens_estimate, r.data.truncated)
```

---

## 7. `append`

Append one message to the session's ordered log. Triggers decision extraction on assistant messages and, when the unsummarized backlog exceeds `summarization_trigger_tokens`, a summarization pass.

### Signature

```python
append(message: Message) -> None
```

### Input

| Param | Required | Description |
|---|---|---|
| `message` | yes | [`Message`](#message-decision-conversationsummary) (`role`, `content`, `created_at`, optional `id` / `metadata`) |

Single-writer; concurrent appends are serialized.

### Usage

```python
from src.context import Message

conversation.append(
    Message(role="user", content="use Redis for cache", created_at="2026-01-01T00:00:00Z")
)
conversation.append(
    Message(
        role="assistant",
        content="we'll use Redis for caching",
        created_at="2026-01-01T00:00:01Z",
    )
)
```

---

## 8. `summarize`

Return the current rolling conversation summary.

### Signature

```python
summarize(*, force: bool = False) -> ContextResult[ConversationSummary]
```

### Input

| Param | Required | Description |
|---|---|---|
| `force` | no | Recompute even if under the trigger threshold (default `False`) |

Without a chat-model wired in: naive truncation fallback, `meta.degraded=True`, `reason="no_chat_model_configured"`.  
If a chat-model is configured but raises: same fallback, `reason="summarizer_unavailable"`.

### Output (`data`: `ConversationSummary`)

| Field | Type | Description |
|---|---|---|
| `text` | `str` | Summary text |
| `covers_through_message_id` | `str` | Last message id covered |
| `created_at` | `str` | ISO-8601 |
| `tokens_estimate` | `int` | Size hint |

### Usage

```python
r = conversation.summarize(force=True)
print(r.data.text)
print(r.meta.degraded, r.meta.reason)
```

---

## 9. `retrieve`

Keyword (and optional embedding) search over this session's own history — Conversation Manager's analogue of RNA's `semantic_search`.

### Signature

```python
retrieve(query: str, *, limit: int = 10) -> ContextResult[list[Message]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `query` | yes | Natural-language / keyword query |
| `limit` | no | Max messages (default 10) |

### Output (`data`: `list[Message]`)

Ranked by keyword overlap + decision boost + recency.

### Usage

```python
r = conversation.retrieve("caching strategy", limit=5)
for m in r.data:
    print(m.role, m.content[:80])
```

---

## 10. `get_decisions`

Return extracted architecture / coding-preference / plan / constraint statements.

### Signature

```python
get_decisions(*, category: DecisionCategory | None = None, limit: int = 20) -> ContextResult[list[Decision]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `category` | no | `"architecture"` / `"coding_preference"` / `"plan"` / `"constraint"`; `None` = all |
| `limit` | no | Max decisions (default 20), most recent first |

### Output (`data`: `list[Decision]`)

| Field | Type | Description |
|---|---|---|
| `category` | `DecisionCategory` | Decision kind |
| `statement` | `str` | Extracted statement |
| `source_message_id` | `str` | Originating message |
| `created_at` | `str` | ISO-8601 |
| `confidence` | `float` | Extraction confidence 0–1 |

Rule-based extraction always runs. Optional LLM pass is off by default (`decision_extraction_llm_enabled=False`).

### Usage

```python
r = conversation.get_decisions(category="architecture")
for d in r.data:
    print(d.confidence, d.statement)
```

---

## 11. `get_recent`

Last N messages for the session, optionally filtered by role.

### Signature

```python
get_recent(*, n: int = 20, roles: tuple[MessageRole, ...] | None = None) -> ContextResult[list[Message]]
```

### Input

| Param | Required | Description |
|---|---|---|
| `n` | no | Max messages (default 20) |
| `roles` | no | Filter e.g. `("user", "assistant")`; `None` = all |

### Output (`data`: `list[Message]`)

Chronological order (oldest → newest within the window).

### Usage

```python
r = conversation.get_recent(n=10, roles=("user", "assistant"))
for m in r.data:
    print(m.role, m.content[:60])
```

---

## 12. `clear`

Reset session message history and summaries. Decisions survive by default (durable project facts).

### Signature

```python
clear(*, keep_decisions: bool = True) -> None
```

### Input

| Param | Required | Description |
|---|---|---|
| `keep_decisions` | no | Keep extracted decisions (default `True`) |

### Usage

```python
conversation.clear()                       # keep decisions
conversation.clear(keep_decisions=False)   # full reset
```

---

## 13. `ExecutionContext`

Immutable runtime state for one execution. Not a manager — only state. Every stage writes exactly one slice via `with_*()`.

### Construction

```python
from src.context import ExecutionContext, RequestContext

ctx = ExecutionContext(
    request=RequestContext(
        request_id="req-1",
        session_id="session-123",
        user_query="add caching to pkg/parser.py",
        repo_path=str(repo),
        requesting_agent="planner",
        task_complexity="MEDIUM",
        created_at="2026-01-01T00:00:00Z",
    )
)
```

### Functional updates

```python
# After Context Manager resolve:
ctx = ctx.with_repository(package.repository).with_conversation(package.conversation)

# Planner:
from src.context import PlanningContext
ctx = ctx.with_planning(PlanningContext(plan_steps=("read parser", "add cache"), current_step=0))

# Events / metrics:
ctx = ctx.with_event("context_resolved", {"tokens": package.tokens_estimate})
print(ctx.version)       # increments on every with_*
print(ctx.checkpoint())  # identity — object *is* the checkpoint
print(ctx.to_dict())     # JSON-serializable
```

### Sub-contexts (ownership)

| Slice | Written by | Contains |
|---|---|---|
| `request` | Orchestrator (once) | Query, session, complexity |
| `repository` | Context Manager (and orchestrator fold from `context.resolve`) | Ranked repo facts / working set |
| `conversation` | Context Manager (and orchestrator fold from resolve) | Memory slice for this step |
| `planning` | Agent via `plan.set_tasks` | Plan steps / checklist tasks |
| `execution` | Orchestrator / agent tools | Code changes, tool results, status |
| `verification` | Orchestrator / verify tools | Tests, harness, checks_required |
| `metrics` | Whichever stage just ran | Token usage, per-stage cost |
| `events` | Every stage (append-only) | Structured event log |

---

## `ContextRequest`

Input to `resolve` / `expand`.

| Field | Type | Description |
|---|---|---|
| `task_description` | `str` | What the requesting agent is doing now |
| `task_complexity` | `"SIMPLE"` / `"MEDIUM"` / `"COMPLEX"` | Drives how much retrieval is planned (orchestrator maps `fast`/`deep`; not soft-phase routing) |
| `requesting_agent` | `"planner"` / `"coder"` / `"verifier"` / `"reviewer"` | Contract the package is validated against |
| `file_hints` | `tuple[str, ...]` | Known file anchors (priority over auto-detect) |
| `symbol_hints` | `tuple[str, ...]` | Known symbol anchors |
| `conversation_query` | `str \| None` | Override query for conversation retrieve; default = `task_description` |
| `token_budget` | `int \| None` | Per-request budget override |
| `capabilities` | `tuple[str, ...] \| None` | Explicit `rna.*` method names; bypasses Requirement Analysis |
| `session_id` | `str \| None` | Session scope for security checks |

### Usage

```python
ContextRequest(
    task_description="verify parser changes",
    task_complexity="MEDIUM",
    requesting_agent="verifier",
    file_hints=("pkg/parser.py",),
)
```

---

## `Message` / `Decision` / `ConversationSummary`

**`Message`**

| Field | Type | Description |
|---|---|---|
| `role` | `"user"` / `"assistant"` / `"system"` / `"tool"` | Speaker |
| `content` | `str` | Text |
| `created_at` | `str` | ISO-8601 |
| `id` | `str` | Assigned on append if empty |
| `metadata` | `dict[str, str]` | Optional extras |

**`Decision`**

| Field | Type | Description |
|---|---|---|
| `category` | `DecisionCategory` | See [`get_decisions`](#10-get_decisions) |
| `statement` | `str` | Extracted statement |
| `source_message_id` | `str` | Origin message |
| `created_at` | `str` | ISO-8601 |
| `confidence` | `float` | 0–1 |

**`ConversationSummary`** — see [`summarize`](#8-summarize) output table.

---

## `RepositoryContext` / `ConversationContext`

**`RepositoryContextItem`**

| Field | Type | Description |
|---|---|---|
| `kind` | `ItemKind` | `file` / `symbol` / `import_edge` / `call_edge` / `test_link` / `workflow_step` / `search_hit` / `semantic_hit` |
| `payload` | RNA model (or path string) | Untouched RNA type when possible |
| `relevance` | `float` | Ranker score 0–1 |
| `tokens_estimate` | `int` | Size hint |
| `source_method` | `str` | e.g. `"get_symbol"` |

**`RepositoryContext`:** `items`, `tokens_estimate`, `truncated`, optional `degraded` / `reason`.

**`ConversationContext`:** `recent_messages`, `summary`, `relevant_history`, `decisions`, `tokens_estimate`, `truncated`.

---

## Helpers

### `build_context_subsystem(rna, session_id, config=None, *, repo_path=None, chat_model=None)`

Canonical construction — returns `(ContextManager, ConversationManager)`.

```python
cm, conversation = build_context_subsystem(rna, "session-123", repo_path=repo)
```

### Fakes (for Agent Layer unit tests)

```python
from src.context import FakeContextManager, FakeConversationManager, ContextRequest, Message

cm = FakeContextManager()
conv = FakeConversationManager(session_id="test")
conv.append(Message(role="user", content="hi", created_at="t"))
pkg = cm.resolve(ContextRequest(
    task_description="hi",
    task_complexity="SIMPLE",
    requesting_agent="coder",
))
```

Zero repository, zero RNA, zero SQLite.

---

## When to use which

| Goal | Call |
|---|---|
| Build context for a Planner/Coder/Verifier/Reviewer step | `cm.resolve(ContextRequest(...))` |
| Need one more file mid-edit without full recompute | `cm.expand(package, additional=...)` |
| Repo changed under an existing package | `cm.refresh(package)` |
| Discard stale package cache | `cm.invalidate()` |
| Reassemble from checkpointed slices | `cm.compose(...)` then `cm.cache(...)` |
| Record a user/assistant turn | `conversation.append(Message(...))` |
| Compact long history | `conversation.summarize(force=True)` |
| Find earlier discussion by meaning | `conversation.retrieve(query)` |
| Recall durable decisions | `conversation.get_decisions()` |
| Last few turns for the prompt | `conversation.get_recent(n=...)` |
| Hold whole-run state across stages | `ExecutionContext` + `with_*()` |

---

## Config reference (`ContextConfig`)

| Field | Default | Notes |
|---|---|---|
| `cache_dir` | `<repo>/.context_cache` | Separate from RNA's `.rna_cache` |
| `max_context_tokens` | `8_000` | Hard budget (system-wide constant) |
| `max_files` | `5` | Max `file` items in a package |
| `max_lines_per_file` | `200` | Same default as `RnaConfig.max_lines_per_file` |
| `conversation_reserve_ratio` | `0.25` | Fraction of token budget reserved for conversation |
| `summarization_trigger_tokens` | `3_000` | Unsummarized backlog before auto-summarize |
| `decision_extraction_llm_enabled` | `False` | Opt-in chat-model-assisted decisions |
| `memory_embedding_model` | `"hash"` | or `"sentence-transformers"` (independent of RNA) |
| `l1_cache_size` | `256` | In-process package-cache LRU |
| `cache_enabled` | `True` | Disable for always-fresh (slower) |
| `retrieval_timeout_ms` | `5_000` | Per RNA call inside one plan |
| `w_hint` / `w_confidence` / `w_recency` / `w_relation` / `w_distance` | `0.40` / `0.20` / `0.15` / `0.15` / `0.10` | Ranker weights |

---

## Pipeline (short)

```text
ContextRequest
  → RequirementAnalyzer   (deterministic rules by agent + complexity)
  → RetrievalPlanner      (RNA + Conversation Manager, concurrent)
  → Aggregator            (flatten RnaResult → RepositoryContextItem)
  → Ranker                (deterministic scores)
  → Compressor            (token / file / line budgets)
  → Validator             (contracts + session boundary)
  → ContextPackage
```

Missing RNA / LLM signals **degrade** (`meta.degraded`); only session-boundary violations **raise** `ContextSecurityError`.

---

## Design docs

| Doc | Contents |
|---|---|
| [`docs/README.md`](docs/README.md) | Vision, principles, non-goals |
| [`docs/01_architecture.md`](docs/01_architecture.md) | Component diagram, dependency graph, lifecycle, degradation |
| [`docs/02_api_spec.md`](docs/02_api_spec.md) | Full wire contract |
| [`docs/03_context_composition.md`](docs/03_context_composition.md) | Context Manager internal pipeline |
| [`docs/04_conversation_memory.md`](docs/04_conversation_memory.md) | Conversation Manager internals |
| [`docs/05_execution_context.md`](docs/05_execution_context.md) | Runtime state, ownership, reconciliation |
| [`docs/06_contract_and_safety.md`](docs/06_contract_and_safety.md) | Safety, observability, testing |
| [`docs/07_implementation_plan.md`](docs/07_implementation_plan.md) | Phase-by-phase build plan |
