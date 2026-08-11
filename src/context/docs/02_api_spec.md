# Context Subsystem — API Specification

This is the full wire contract: every data model, and the complete signature/behavior of `ContextManagerPort` and `ConversationManagerPort`. Both ports follow the exact same envelope discipline RNA established in its own `02_api_spec.md` — every method that can degrade or partially fail returns a `ContextResult[T]`, never a bare value.

## 1. Common envelope

```python
# context/models.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Generic, Literal, TypeVar

T = TypeVar("T")

@dataclass(frozen=True, slots=True)
class ContextMeta:
    cost_ms: float
    cache_hit: bool
    truncated: bool
    degraded: bool = False
    reason: str | None = None
    error: str | None = None
    tokens_estimate: int = 0
    sources: tuple[str, ...] = ()   # subset of {"rna", "conversation", "cache"}

@dataclass(frozen=True, slots=True)
class ContextResult(Generic[T]):
    data: T
    meta: ContextMeta

    def to_dict(self) -> dict[str, Any]:
        return {"data": _to_jsonable(self.data), "meta": asdict(self.meta)}
```

`meta.sources` is the one addition beyond RNA's `RnaMeta` shape: because a `ContextPackage` is always a merge of up to three origins (RNA, Conversation Manager, and the package cache), every result names which of them actually contributed, so a caller (or an auditor reading a log) can tell a conversation-only degraded package apart from a full package at a glance, without inspecting `data`.

`ContextError` (invariant violations only — see `06_contract_and_safety.md` §1) is the only exception type either port raises. Everything else is a soft miss surfaced through `meta`.

---

## 2. Shared enums

```python
TaskComplexity = Literal["SIMPLE", "MEDIUM", "COMPLEX"]        # docs/02_specs.md S6
RequestingAgent = Literal["planner", "coder", "verifier", "reviewer"]
ItemKind = Literal[
    "file", "symbol", "import_edge", "call_edge",
    "test_link", "workflow_step", "search_hit", "semantic_hit",
]
MessageRole = Literal["user", "assistant", "system", "tool"]
DecisionCategory = Literal["architecture", "coding_preference", "plan", "constraint"]
```

`TaskComplexity` is the system-wide `{SIMPLE, MEDIUM, COMPLEX}` enum. Today the orchestrator maps runtime mode (`fast`→SIMPLE, `deep`→COMPLEX) into `RequestContext.task_complexity`; the model may also pass complexity on `context.resolve`. The Context Manager's Requirement Analyzer keys its retrieval rules off this enum (`03_context_composition.md` §2) so "how much should this task cost" stays consistent. It does **not** select soft agent phases or CompletionPolicy outcomes — those are independent (see [`../../orchestrator/README.md`](../../orchestrator/README.md)).

---

## 3. `ContextManagerPort`

```python
class ContextManagerPort(Protocol):
    """Composes a bounded, ranked context package for one agent step. Never calls an LLM."""

    def resolve(self, request: ContextRequest) -> ContextResult[ContextPackage]: ...
    def expand(self, package: ContextPackage, *, additional: ContextRequest) -> ContextResult[ContextPackage]: ...
    def refresh(self, package: ContextPackage) -> ContextResult[ContextPackage]: ...
    def invalidate(self, scope: str | None = None) -> None: ...
    def cache(self, package: ContextPackage) -> None: ...
    def compose(
        self,
        *,
        repository: RepositoryContext | None = None,
        conversation: ConversationContext | None = None,
        budget: int | None = None,
    ) -> ContextResult[ContextPackage]: ...
```

### 3.1 `resolve`

The primary entry point. Runs the full pipeline (`01_architecture.md` §4): Requirement Analysis -> Retrieval Planning -> RNA + Conversation Manager query -> Aggregation -> Ranking -> Compression -> Validation -> `ContextPackage`.

| Param | Required | Description |
|---|---|---|
| `request` | yes | A `ContextRequest` (§5) |

Returns `ContextResult[ContextPackage]`. Never raises except `ContextSecurityError` for a scope/session boundary violation.

### 3.2 `expand`

Widens an already-resolved package without recomputing it from scratch — for a follow-up step that needs "everything from before, plus one more file" (a common Coder-Agent pattern: it read the plan's context, then asks for one additional symbol it discovered mid-edit).

| Param | Required | Description |
|---|---|---|
| `package` | yes | A previously resolved `ContextPackage` |
| `additional` | yes | A `ContextRequest` describing only the delta |

Every item already in `package` is re-validated against its stored content hash (cheap) rather than re-fetched; only the delta implied by `additional` triggers new RNA/Conversation Manager calls. If budget is exceeded after merging, the same Compressor pass from `resolve` re-runs over the union.

### 3.3 `refresh`

Recomputes a package because the underlying repository or conversation state is known to have changed (e.g. the Executor just applied a patch to a file that was in context). Equivalent to `invalidate(scope)` for the package's own scope followed by `resolve()` against the same stored `request`.

| Param | Required | Description |
|---|---|---|
| `package` | yes | The package to refresh (its stored `request` is replayed) |

### 3.4 `invalidate`

```python
context_manager.invalidate("pkg/parser.py")   # one scope
context_manager.invalidate()                   # everything
```

Clears the package cache for one scope or entirely — mirrors `rna.invalidate()` exactly (`06_contract_and_safety.md` §2). Does not touch RNA's own cache; RNA invalidates itself independently when it detects content changes.

### 3.5 `cache`

Explicitly persists a package that was built via `compose()` (bypassing `resolve()`'s own automatic caching) — used when the caller already has repository/conversation slices in hand (e.g. re-assembling a package from a checkpointed `ExecutionContext` after a resume) and wants it available to future `resolve()`/`expand()` calls without a redundant retrieval pass.

### 3.6 `compose`

The pure merge-only entry point: given already-fetched `RepositoryContext` and/or `ConversationContext`, run Aggregation -> Ranking -> Compression -> Validation and return a `ContextPackage`, without ever calling RNA or the Conversation Manager itself. `resolve()` is implemented as *retrieve, then delegate to `compose()`* — `compose()` is not a shortcut that skips validation, it is the shared tail of the pipeline both `resolve()` and `expand()` funnel through, so ranking/compression/validation logic is never duplicated between them.

---

## 4. `ConversationManagerPort`

```python
class ConversationManagerPort(Protocol):
    """Owns conversational memory for one session. No repository knowledge, no RNA dependency."""

    def append(self, message: Message) -> None: ...
    def summarize(self, *, force: bool = False) -> ContextResult[ConversationSummary]: ...
    def retrieve(self, query: str, *, limit: int = 10) -> ContextResult[list[Message]]: ...
    def get_decisions(self, *, category: DecisionCategory | None = None, limit: int = 20) -> ContextResult[list[Decision]]: ...
    def get_recent(self, *, n: int = 20, roles: tuple[MessageRole, ...] | None = None) -> ContextResult[list[Message]]: ...
    def clear(self, *, keep_decisions: bool = True) -> None: ...
```

### 4.1 `append`

Appends one message to the session's ordered log. Triggers the decision-extraction pass (`04_conversation_memory.md` §3) and, if the unsummarized backlog now exceeds `summarization_trigger_tokens`, schedules (but does not block on) a summarization pass. Single-writer; see `01_architecture.md` §6.

### 4.2 `summarize`

| Param | Required | Description |
|---|---|---|
| `force` | no | Recompute even if under the trigger threshold |

Returns the current rolling `ConversationSummary`. On chat-model failure, falls back to a naive join of the oldest unsummarized messages and sets `meta.degraded=True` (`01_architecture.md` §5).

### 4.3 `retrieve`

Meaning/keyword-based search over stored history — the Conversation Manager's equivalent of RNA's `semantic_search`, scoped to this session's own messages instead of the repository.

| Param | Required | Description |
|---|---|---|
| `query` | yes | Natural-language query (usually the current task description) |
| `limit` | no | Max messages (default 10) |

### 4.4 `get_decisions`

| Param | Required | Description |
|---|---|---|
| `category` | no | Filter to one `DecisionCategory`; `None` = all |
| `limit` | no | Max decisions (default 20), most recent first |

### 4.5 `get_recent`

| Param | Required | Description |
|---|---|---|
| `n` | no | Max messages (default 20) |
| `roles` | no | Filter by role; `None` = all roles |

### 4.6 `clear`

```python
conversation_manager.clear()                       # new session, keep decisions
conversation_manager.clear(keep_decisions=False)     # full reset
```

Resets message history and summaries for the session. Decisions (architecture/coding-preference records) survive by default, since they represent durable facts about the project, not conversational turns — a deliberate asymmetry, the same way RNA's cache survives session boundaries while its L1 in-memory layer does not.

---

## 5. `ContextRequest`

```python
@dataclass(frozen=True, slots=True)
class ContextRequest:
    task_description: str
    task_complexity: TaskComplexity
    requesting_agent: RequestingAgent
    file_hints: tuple[str, ...] = ()
    symbol_hints: tuple[str, ...] = ()
    conversation_query: str | None = None      # defaults to task_description
    token_budget: int | None = None             # overrides ContextConfig.max_context_tokens
    capabilities: tuple[str, ...] | None = None  # explicit rna.* method names; None = auto-planned
```

| Field | Description |
|---|---|
| `task_description` | What the requesting agent is trying to do right now — feeds Requirement Analysis and, by default, Conversation Manager retrieval |
| `task_complexity` | The system-wide `{SIMPLE, MEDIUM, COMPLEX}` enum; drives how much the Requirement Analyzer is willing to fetch (`03_context_composition.md` §2) |
| `requesting_agent` | Which contract the Validator checks the resulting package against (`03_context_composition.md` §6) |
| `file_hints` / `symbol_hints` | Known scope anchors (e.g. the file the Coder is currently editing) — always take priority over auto-detected scope |
| `conversation_query` | Overrides the query text sent to `conversation_manager.retrieve()`; `None` reuses `task_description` |
| `token_budget` | Per-request override of the configured default budget, for callers that legitimately need more or less (e.g. Reviewer needs less code, more test/diff context) |
| `capabilities` | Escape hatch: explicit RNA method names to call, bypassing Requirement Analysis entirely — for callers that already know exactly what they need |

---

## 6. Repository-side models

```python
@dataclass(frozen=True, slots=True)
class RepositoryContextItem:
    kind: ItemKind
    payload: Any            # one of RNA's models.py types (SymbolRef, FileSlice, CallEdge, ...)
    relevance: float          # 0.0-1.0 ranking score, assigned by the Ranker
    tokens_estimate: int
    source_method: str         # e.g. "get_symbol", "get_callers" -- which rna.* call produced it

@dataclass(frozen=True, slots=True)
class RepositoryContext:
    items: tuple[RepositoryContextItem, ...]
    tokens_estimate: int
    truncated: bool
    degraded: bool = False
    reason: str | None = None
```

`RepositoryContextItem.payload` is deliberately typed `Any` rather than a subsystem-specific wrapper: it holds the exact RNA model instance (`SymbolRef`, `FileSlice`, `CallEdge`, `TestLink`, `WorkflowStep`, `SearchHit`, `SemanticHit`) untouched, so nothing is lost or re-shaped in translation and RNA's own `confidence`/`degraded` metadata (carried on the originating `RnaResult`, folded into the item at Aggregation time) is never discarded.

---

## 7. Conversation-side models

```python
@dataclass(frozen=True, slots=True)
class Message:
    role: MessageRole
    content: str
    created_at: str                     # ISO-8601
    metadata: dict[str, str] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class Decision:
    category: DecisionCategory
    statement: str
    source_message_id: str
    created_at: str
    confidence: float                    # extraction confidence, 0.0-1.0

@dataclass(frozen=True, slots=True)
class ConversationSummary:
    text: str
    covers_through_message_id: str
    created_at: str
    tokens_estimate: int

@dataclass(frozen=True, slots=True)
class ConversationContext:
    recent_messages: tuple[Message, ...]
    summary: ConversationSummary | None
    relevant_history: tuple[Message, ...]
    decisions: tuple[Decision, ...]
    tokens_estimate: int
    truncated: bool
```

---

## 8. `ContextPackage`

```python
@dataclass(frozen=True, slots=True)
class ContextPackage:
    request: ContextRequest
    repository: RepositoryContext
    conversation: ConversationContext
    tokens_estimate: int
    token_budget: int
    truncated: bool
    provenance: tuple[str, ...]     # human-readable trace of what was included/dropped and why
    created_at: str
    cache_key: str
```

`provenance` exists so every package is self-explaining without needing to replay logs: e.g. `("get_tests: dropped (budget) - 3 lowest-ranked test_link items", "conversation.relevant_history: truncated to 4 messages (floor priority)")`. This satisfies the system-wide "logs must exist for every state" invariant (`docs/02_specs.md` §8) at the package level, not just in the observability log stream (`06_contract_and_safety.md` §4).

---

## 9. Config reference (`ContextConfig`)

```python
class ContextConfig(BaseModel):
    cache_dir: Path | None = None                       # default: <repo>/.context_cache
    max_context_tokens: int = 8_000                       # docs/03_architecture.md S4.4, shared constant
    max_files: int = 5                                     # docs/03_architecture.md S4.4
    max_lines_per_file: int = 200                            # docs/03_architecture.md S4.4, same as RnaConfig
    conversation_reserve_ratio: float = 0.25                   # fraction of max_context_tokens reserved for conversation
    summarization_trigger_tokens: int = 3_000
    decision_extraction_llm_enabled: bool = False
    memory_embedding_model: str = "hash"                          # "hash" | "sentence-transformers" -- mirrors RnaConfig
    l1_cache_size: int = 256
    cache_enabled: bool = True
    retrieval_timeout_ms: int = 5_000                                # per rna.* call, inside one RetrievalPlan
```

`max_context_tokens`, `max_files`, and `max_lines_per_file` default to exactly the values already fixed as system-wide invariants (`docs/03_architecture.md` §4.4). They are configurable per the same rule the top-level design already states: *"Values may be tuned per deployment or model; the presence of hard limits is fixed."* `max_lines_per_file` matching `RnaConfig.max_lines_per_file` is intentional — a file the Context Manager includes should never be truncated to a different length than `rna.get_file` itself would have applied by default, so the two layers never disagree about "how much of this file is reasonable to show."
