# Context Subsystem — Consumption Contract, Safety, Observability & Testing

## 1. How agents consume these ports

Unlike RNA, the Context Subsystem is **not** exposed to a model as a callable tool. RNA is deliberately agent-facing infrastructure — something a model decides to invoke mid-reasoning (`rna/docs/README.md` §1). The Context Subsystem sits one layer below that: it is host-side infrastructure the Planner/Coder/Verifier/Reviewer **use to build their next model call's input**, before that call happens. A model never sees `context_manager.resolve(...)` as a tool it can choose to invoke — it only ever sees the resulting, already-composed prompt content.

Concretely, this means:

- `ContextManagerPort` and `ConversationManagerPort` are **constructor-injected dependencies** of the Agent Layer, the same way `RnaPort` is a constructor-injected dependency of the Context Manager itself (`01_architecture.md` §2). No MCP server, no function-calling schema generation — those are RNA-specific concerns (`rna/docs/05_tool_contract_and_safety.md` §1-2) that do not apply here.
- Every Agent Layer component receives a `ContextManagerPort` and never an `RnaPort`. This is enforced structurally by never wiring an `RnaPort` reference into the Planner/Executor/Verifier/Reviewer's constructors at all — there is nothing to accidentally call, not just a convention not to call it (`01_architecture.md` §2, invariant 1).
- `FakeContextManager`/`FakeConversationManager` (§5) are the default dependency for any Agent Layer component's own unit tests — a Planner test never needs a real repository, a real RNA instance, or real SQLite files on disk.

### Safety boundary

The Context Subsystem's safety boundary is narrower than RNA's (it never touches the filesystem or spawns a subprocess directly), but it still enforces:

| Rule | Enforcement |
|---|---|
| No repository writes | The Context Subsystem never calls anything on `RnaPort` beyond its read-only methods; it inherits RNA's own read-only guarantee transitively and adds nothing that could write (`rna/docs/README.md` §5, §8) |
| No path escapes | Path/scope validation for repository content is RNA's own job (`RnaSecurityError`, `rna/docs/01_architecture.md` §6) and is **not** re-implemented here — the Context Manager passes `file_hints` straight through to RNA and trusts RNA's own boundary check, rather than maintaining a second, potentially-inconsistent path-validation implementation |
| No cross-session leakage | Every `ConversationManager` instance is bound to exactly one `session_id` at construction; a `Message`/`Decision`/`ConversationContext` item ever surfacing under a different session id is the one condition unique to this subsystem that raises `ContextSecurityError` immediately, never degrades (`04_conversation_memory.md` §1) |
| No hidden LLM calls in the composition hot path | `resolve()`, `expand()`, `refresh()`, `compose()` never call a chat model. Only `Conversation Manager.summarize()` and the optional decision-extraction pass do, and only through the system's existing chat-model port (`docs/02_specs.md` §10) — never a new, subsystem-specific model integration |
| Cache is process/machine-local only | `.context_cache/` is never transmitted anywhere, exactly like `.rna_cache/` — a local performance optimization, not a data store with its own access-control surface (`rna/docs/05_tool_contract_and_safety.md` §3) |

```python
class ContextError(Exception):
    """Base Context Subsystem error."""

class ContextSecurityError(ContextError):
    """Cross-session/cross-scope boundary violation. Reserved for invariant violations."""

class ContextConfigError(ContextError):
    """Invalid ContextConfig detected at startup."""
```

This is a deliberate, near-exact mirror of `rna/errors.py` — same three-error shape, same "reserved for invariant violations, not soft misses" doctrine (`01_architecture.md` §5).

---

## 2. Cache reuse, not reinvention

Both `manager/cache.py` and the Conversation Manager's stores compose primitives RNA already built rather than re-solving the same problem:

| Need | RNA's existing solution | Context Subsystem's reuse |
|---|---|---|
| Compute-once-under-lock, L1 LRU + L2 SQLite | `rna.cache.store.CacheStore` | `manager/cache.py` instantiates `CacheStore` directly, pointed at `.context_cache/packages/` (`03_context_composition.md` §8) |
| Repository staleness fingerprint | `rna.repo_analyzer.fingerprint.repo_fingerprint` | Context Manager calls RNA's fingerprint function rather than deriving its own notion of "has the repo changed" (`03_context_composition.md` §1) |
| Content-hash cache keys | `rna.cache.keys.make_cache_key` | Same key-construction pattern, same tuple shape (`repo_fingerprint`/`subject_hash`/`method_name`/`params`), extended with a `conversation_state_hash` component that is unique to this subsystem |
| Offline-by-default embedding option | `RnaConfig.embedding_model: "hash" \| "sentence-transformers"` | `ContextConfig.memory_embedding_model` mirrors the same two named options for configuration consistency, but is a fully independent instance/index (`04_conversation_memory.md` §5) — no code or data is shared, only the *shape* of the choice |

Nothing here re-implements a cache, a fingerprint algorithm, or a locking strategy. Every one of these is "the same kind of problem RNA already solved" rather than "a problem unique to this subsystem," so it is solved by composition.

---

## 3. Observability

Every `ContextManagerPort`/`ConversationManagerPort` call emits one structured log record, in the same shape RNA already commits to (`rna/docs/05_tool_contract_and_safety.md` §4):

```python
{
    "method": "resolve",
    "requesting_agent": "planner",
    "task_complexity": "MEDIUM",
    "cost_ms": 118.4,
    "cache_hit": False,
    "truncated": True,
    "degraded": False,
    "sources": ("rna", "conversation"),
    "tokens_estimate": 5920,
}
```

For `ConversationManager.summarize()`/decision extraction specifically, the log additionally records whether the chat-model port was actually invoked (`"llm_invoked": True/False`) — the one place in this subsystem where a "network egress"-equivalent event matters, mirroring how RNA distinctly flags `google_search`'s network egress (`rna/docs/05_tool_contract_and_safety.md` §4).

Because every `ContextPackage` also self-documents its own `provenance` (`02_api_spec.md` §8), a complete audit of "what did this agent step actually see, and why" never requires replaying logs — the package itself is the record, and the log stream is the timing/cost overlay on top of it.

---

## 4. Testing strategy

| Layer | Approach |
|---|---|
| Port contract | One test suite run against `FakeContextManager`/`FakeConversationManager` *and* the real implementations (parametrized), asserting both satisfy `ContextManagerPort`/`ConversationManagerPort` identically in shape — guarantees Agent Layer tests never need a real repository or real RNA instance |
| Requirement Analyzer | Golden-table tests: for every `(requesting_agent, task_complexity)` pair, assert the exact planned RNA call list (`03_context_composition.md` §2) |
| Aggregator | Pure unit tests against hand-built `RnaResult` fixtures — no RNA instance, no I/O |
| Ranker / Compressor | Deterministic-by-construction: same input list -> same output list, every time. Snapshot tests lock in exact ordering and drop decisions for a fixed fixture set, so a future weight change is a visible, deliberate diff, never a silent behavior drift |
| Validator | Unit tests per contract (`requesting_agent`) asserting the correct `provenance` entries appear for a deliberately incomplete package, and that a cross-session item triggers `ContextSecurityError` |
| Message Store / Decision Extractor / Summarizer | Unit tests against a fixture message sequence; the chat-model-dependent paths (opt-in decision extraction, summarization) are tested through a fake chat-model port implementation, never a real model call, and a "chat-model raises" fixture asserts the documented degrade-not-throw behavior (`01_architecture.md` §5) |
| Package cache | Reuses the exact same test technique RNA's own `CacheStore` tests use (simulate content changes, assert exact invalidation scope) — since it is the same class |
| End-to-end pipeline | One integration test wires a `FakeRna` (`tests/doubles/rna.py`) into a real `ContextManager`, exercising the full `resolve()` pipeline without a real repository, real language tools, or real subprocesses — the same "fast, deterministic, safe for CI" posture `FakeRna` already gives every other host application in this codebase |

`FakeContextManager`/`FakeConversationManager` in `tests/doubles/context.py` are scripted and deterministic (no SQLite, no threads, no RNA dependency), exactly the role `FakeRna` plays for RNA (`rna/docs/05_tool_contract_and_safety.md` §5) — test doubles live outside production packages.
