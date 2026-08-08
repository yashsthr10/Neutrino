# Conversation Manager — Memory Pipeline

The Conversation Manager has no dependency on RNA, the Context Manager, or `ExecutionContext`. It is queried, never orchestrated — a fact reflected in the dependency graph (`01_architecture.md` §2) and worth restating here: nothing in this document ever imports `src.rna` or `src.context.manager`.

```text
Message
   │
   ▼
Message Store         (message_store.py)
   │
   ▼
Decision Extraction     (decision_extractor.py)
   │
   ▼
Summarization             (summarizer.py)
   │
   ▼
Memory Index                 (memory_index.py)
   │
   ▼
Retrieval                        (retriever.py)
```

`append()` drives the first three stages synchronously-in-order (store, then extract, then conditionally summarize); Memory Index update happens as part of `append()` too (index the new message immediately, cheap for the keyword index, batched for the optional embedding index). Retrieval is a separate read path, triggered by `retrieve()`/`get_recent()`/`get_decisions()`, never by `append()`.

---

## 1. Message Store

**Class:** `message_store.MessageStore` — an append-only log, one row per `Message`, backed by SQLite (same technology choice as RNA's own `cache/store.py` and `embedding_engine/vector_store.py`, for the same reason: durable, zero-external-dependency, trivially inspectable).

```sql
CREATE TABLE messages (
    id            TEXT PRIMARY KEY,      -- ULID/UUID, sortable by creation order
    session_id    TEXT NOT NULL,
    role          TEXT NOT NULL,          -- MessageRole
    content       TEXT NOT NULL,
    created_at    REAL NOT NULL,
    metadata_json TEXT NOT NULL,           -- dict[str, str], serialized
    token_count   INTEGER NOT NULL
);
CREATE INDEX idx_messages_session ON messages(session_id, created_at);
```

`session_id` is not optional and is never inferred — every `ConversationManager` instance is constructed for exactly one session, and every row it ever writes or reads is scoped to that session id. This is the concrete invariant the Validator's scope-boundary check (`03_context_composition.md` §7) and `ContextSecurityError` (`06_contract_and_safety.md` §1) exist to protect: **a `ConversationManager` instance must never return a row belonging to a different `session_id`, under any code path, even a cache bug.**

`append()` acquires a single-writer lock (`01_architecture.md` §6) before inserting, because every downstream stage — decision extraction, summarization, the memory index — assumes it is operating over a strictly ordered, gap-free log for one session.

---

## 2. Retention

The message store is never pruned by a background job; it is bounded the same way RNA bounds everything — by what a caller actually asks for (`get_recent(n=...)`), not by silently deleting history. The one place data volume is actively reduced is Summarization (§4), which folds old messages into a compact summary without deleting the underlying rows — the full transcript remains available (e.g. for audit or `get_recent` with a large `n`) even after it has been summarized for context-budget purposes.

`clear()` is the only path that deletes rows, and only on an explicit caller request (`02_api_spec.md` §4.6) — e.g. an operator-triggered `/clear` at the TUI level, never automatic.

---

## 3. Decision Extraction

**Class:** `decision_extractor.DecisionExtractor`

Runs on every `append()` where `role == "assistant"` (decisions are things *stated*, and in this system that means stated by the assistant after reasoning about a user's request — a user's raw message is a request, not yet a decision).

Two passes, composed rather than exclusive:

1. **Rule-based pass (always runs).** A fixed set of trigger phrases/patterns per `DecisionCategory` — `"we'll use "`, `"decided to "`, `"going with "`, `"the convention here is "`, `"instead of X, use Y"` — extracted via regex against sentence-segmented content. Zero cost, zero external dependency, always available. This is the tier that guarantees decision tracking never goes to zero even with no LLM configured.
2. **Chat-model-assisted pass (opt-in, `ContextConfig.decision_extraction_llm_enabled`).** When enabled, a structured extraction call goes through the **existing chat-model port** (`docs/02_specs.md` §10) — the Conversation Manager does not add a new model integration, it is one more caller of the same port the Planner/Coder/Reviewer already use. Prompted to return `{category, statement, confidence}` tuples for anything the rule-based pass missed.

Both passes write to the same `decisions` table; duplicates (near-identical `statement` text within the same session) are collapsed, keeping the higher-confidence extraction.

```sql
CREATE TABLE decisions (
    id                TEXT PRIMARY KEY,
    session_id        TEXT NOT NULL,
    category          TEXT NOT NULL,
    statement         TEXT NOT NULL,
    source_message_id TEXT NOT NULL,
    created_at        REAL NOT NULL,
    confidence        REAL NOT NULL
);
```

On chat-model failure (pass 2), the extractor degrades to rule-based-only for that message and sets `meta.degraded=True`, `reason="extractor_llm_unavailable"` on the next `ContextResult` that surfaces it (`01_architecture.md` §5) — it never blocks `append()` itself, since decision extraction is a side effect of storing a message, not a precondition for it.

---

## 4. Summarization

**Class:** `summarizer.Summarizer`

Triggered automatically inside `append()` when the token count of messages *not yet covered by* the current summary exceeds `ContextConfig.summarization_trigger_tokens` (default 3,000), or explicitly via `summarize(force=True)`.

Rolling/hierarchical strategy: `new_summary = summarize_via_chat_model(old_summary_text, new_messages_since(old_summary.covers_through_message_id))` — each pass folds the previous summary plus only the newly-unsummarized messages, so cost is proportional to new content, not to total session length, the same "on-demand, incremental" posture RNA takes toward repository indexing (`rna/docs/04_indexing_and_caching.md` §1).

Goes through the chat-model port, same as Decision Extraction's optional pass. On failure: fall back to a naive summary — a truncated concatenation of the oldest unsummarized messages — and set `meta.degraded=True`, `reason="summarizer_unavailable"` (`01_architecture.md` §5). A degraded summary is still marked `covers_through_message_id` correctly, so the next successful summarization pass picks up from the right place rather than reprocessing messages the naive fallback already (imperfectly) covered.

```sql
CREATE TABLE summaries (
    id                       TEXT PRIMARY KEY,
    session_id               TEXT NOT NULL,
    text                     TEXT NOT NULL,
    covers_through_message_id TEXT NOT NULL,
    created_at                REAL NOT NULL,
    tokens_estimate            INTEGER NOT NULL
);
```

`get_decisions`/`retrieve`/`get_recent` always read the latest summary row (highest `created_at`); older rows are kept for audit, not deleted.

---

## 5. Memory Index & Retrieval

**Classes:** `memory_index.MemoryIndex`, `retriever.Retriever`

Two tiers, deliberately mirroring RNA's own precision-tier philosophy (`rna/docs/01_architecture.md` §3) at a much smaller scale:

| Tier | Always available? | Backing |
|---|---|---|
| Keyword | Yes | SQLite FTS (or an in-process inverted index for small sessions) over `messages.content` |
| Embedding | Opt-in (`ContextConfig.memory_embedding_model`) | `"hash"` (offline default) or `"sentence-transformers"` — same two named options `RnaConfig.embedding_model` already exposes, for configuration consistency, but a **fully independent index and instance** — conversation memory is never mixed into RNA's own `.rna_cache/embeddings/` store, and no vector ever crosses between the two subsystems |

`retriever.Retriever.retrieve(query, limit)` combines: keyword overlap score + (if enabled) embedding cosine similarity + a recency decay factor + a fixed boost for messages that are also linked to a `Decision` row. Degrades to keyword-only, `meta.degraded=True`, `reason="embedding_index_unavailable"`, if the embedding backend fails to load — never blocks retrieval entirely.

---

## 6. Storage layout

```text
<repo_root>/.context_cache/
  conversation/
    <session_id>/
      messages.sqlite        # Message Store
      decisions.sqlite         # Decision Extraction output
      summaries.sqlite           # Summarizer output
      memory_index/
        keyword.sqlite            # FTS index
        vectors.<backend>           # optional embedding index, only if memory_embedding_model != "hash" is upgraded
```

Scoped per `session_id` on disk, not just per row in a shared table — this makes the "never leak across sessions" invariant (§1) trivially true at the filesystem level as well as the query level: a bug that forgot a `WHERE session_id = ?` clause still cannot read another session's file. `.context_cache/` sits alongside (not inside) RNA's `.rna_cache/` — two independent, machine-local, disposable cache directories, each owned by exactly one subsystem, each safe to delete independently.
