# Context Subsystem — Vision & Principles

> **User-facing reference** (quick start, method index, config): see the package [`../README.md`](../README.md).

## 1. What the Context Subsystem is

The Context Subsystem is the layer that decides **what an agent gets to see**, on every step of a run. It sits between two things that must never touch each other directly:

- **RNA** — a read-only knowledge API that can answer any factual question about the repository, given a specific query.
- **The Agent Layer** (continuous AGENT loop with soft DISCOVER/IMPLEMENT/VERIFY phases) — which needs an already-assembled, already-bounded, already-relevant slice of information to do its job, not a knowledge API to query ad hoc.

Something has to sit in the middle and do the work of turning "what does this task need" into "here is the exact, bounded package of repository facts and conversation memory for this step." That is the Context Subsystem's entire job. It does not plan. It does not write code. It does not decide what to do next. It decides **what is worth knowing right now**, and hands that answer to whoever asked.

It is not one class. It is a **subsystem** of three components with three distinct reasons to change, exactly the way RNA is not one class but six focused engines behind one facade:

```text
Context Subsystem
├── Context Manager        — owns composition: turns a request into a bounded package
├── Conversation Manager   — owns conversational memory: messages, summaries, decisions
└── ExecutionContext       — owns nothing; it is the runtime state container itself
```

---

## 2. Why: what "context assembly" actually requires

Every agent framework that survives contact with a real, non-trivial codebase ends up re-solving the same problem, usually by tangling it into whichever component needed it first:

| Need | Who usually solves it, and how | Context Subsystem component |
|---|---|---|
| "What repository facts does this specific task need?" | Ad hoc — the calling code decides inline what to fetch | Context Manager (Requirement Analyzer) |
| Merge several unrelated fact sources into one prompt-ready blob | String concatenation in the prompt builder | Context Manager (Aggregator) |
| Decide which facts matter more than others when everything can't fit | Usually: nothing, first-fit-wins, or "most recent" | Context Manager (Ranker) |
| Enforce a token/file/line budget | A truncation hack applied late, inconsistently | Context Manager (Compressor) |
| Remember what was said earlier in the session | A raw, ever-growing message list appended to every prompt | Conversation Manager (Message Store + Summarizer) |
| Recall a decision made three turns ago without replaying the whole transcript | Nothing — models re-derive or contradict earlier decisions | Conversation Manager (Decision Extractor + Retriever) |
| Give the continuous AGENT loop a single, consistent view of "where are we in this run" | A shared mutable dict, mutated from everywhere | ExecutionContext (immutable, ownership-partitioned state) |

The Context Subsystem's bet: treat context assembly with the same discipline RNA already applies to repository knowledge — **on-demand, bounded by default, degrade-gracefully, cache-aware, deterministic** — instead of letting every caller reinvent a smaller, worse version of the same pipeline.

---

## 3. Design principles

1. **Composition, not retrieval.** The Context Manager never becomes a second knowledge API. It answers "what should be in context for this task," not "tell me every fact about X." Retrieval is delegated to RNA; composition — requirement analysis, merging, ranking, compressing, validating — is the Context Manager's own, non-duplicated responsibility.
2. **One retrieval path.** Every repository fact an agent ever sees flows through the Context Manager, which is the only component that calls RNA. Planner, Executor, Verifier, and Reviewer never import RNA directly. This keeps the dependency graph one-way and means retrieval policy (what to fetch, how much, when to give up) lives in exactly one place (`01_architecture.md` §3).
3. **Conversation is not repository.** The Conversation Manager owns conversational memory and nothing else. It has no dependency on RNA and no opinion about code. It changes only when long-term memory quality needs to improve, never when retrieval or ranking logic changes.
4. **State is not logic.** ExecutionContext holds data; it computes nothing and decides nothing. Every sub-context inside it (`RequestContext`, `RepositoryContext`, `ConversationContext`, `PlanningContext`, `ExecutionState`, `VerificationContext`, `MetricsContext`, `EventLog`) has exactly one legitimate writer, enforced by immutability, not by convention alone (`05_execution_context.md` §3).
5. **Bounded by default.** Every `ContextPackage` carries an enforced token/file/line budget (same numeric limits the rest of Neutrino already commits to — `MAX_CONTEXT_TOKENS=8000`, `MAX_FILES=5`, `MAX_LINES_PER_FILE=200`). Callers can request more; they never get an unbounded package by accident (`03_context_composition.md` §5).
6. **Cache-first, invalidation-aware.** Anything expensive — a composed package, a conversation summary, a decision extraction pass — is computed once per content fingerprint and reused, using the exact same cache mechanics RNA already validated (`06_contract_and_safety.md` §2).
7. **Deterministic core, no hidden LLM calls in the hot path.** Requirement analysis, retrieval planning, ranking, and compression are rule-based and reproducible — the same request against the same repository and conversation state produces the same package. The one place an LLM is legitimately involved (conversation summarization, optional decision extraction) goes through the **existing chat-model port** (`docs/02_specs.md` §10) — the Context Subsystem never adds its own ad hoc model integration.
8. **Never throw for a soft miss; only throw for an invariant violation.** Missing conversation history, an unreachable RNA facade, or an over-budget request all degrade gracefully with `meta.degraded`/`meta.reason`. Only a genuine boundary violation (e.g. one session reading another session's conversation memory) raises `ContextSecurityError` — the same posture RNA already takes with `RnaSecurityError` (`06_contract_and_safety.md` §1).
9. **Read-only toward the repository, write-only toward its own state.** The Context Subsystem never mutates the repository (that's RNA's read-only guarantee, inherited transitively) and never mutates anyone else's `ExecutionContext` sub-context. It only ever produces new, immutable values for whoever asked.

---

## 4. Component ownership map

| Component | Owns | Changes when |
|---|---|---|
| **Context Manager** | Requirement analysis, retrieval orchestration (via RNA), aggregation, ranking, compression, validation, package caching | Retrieval strategy, ranking heuristics, compression policy, or budget rules improve |
| **Conversation Manager** | Message storage, summarization, decision extraction, memory indexing, history retrieval | Long-term memory quality, summarization strategy, or decision-tracking improves |
| **ExecutionContext** | The full runtime state snapshot of one execution (request, repository, conversation, planning, execution, verification, metrics, events) | The runtime itself needs to track new state |

Each component has exactly one reason to change. That is the entire point of the decomposition — see `01_architecture.md` §1 for the dependency graph this produces.

---

## 5. Non-goals

- The Context Subsystem does **not** analyze code. Every repository fact it packages was computed by RNA; it never re-implements parsing, graph-building, or search.
- The Context Subsystem does **not** decide *what to do* with a task — that is the Planner's job. It only decides what information the Planner (or Coder, Verifier, Reviewer) gets to see while doing its job.
- The Context Manager does **not** hold conversation state, and the Conversation Manager does **not** hold repository state. Neither reaches into the other's storage.
- ExecutionContext does **not** contain behavior. It is a data container with a functional-update API, not a service.
- The Context Subsystem does **not** enforce agent completion, iteration caps, or reviewer gating — that remains the orchestrator's job (`CompletionPolicy` + `AgentPolicy`; see [`../../orchestrator/README.md`](../../orchestrator/README.md) and [`../../agent/README.md`](../../agent/README.md)). The Context Subsystem only supplies the `token_usage`/`MetricsContext` numbers and retrieval packages those policies / prompts consume.
- The Context Subsystem is **not** exposed to the LLM as a callable tool the way RNA is. It is host-side infrastructure that runs *before* a model call to build that call's input, not a tool a model invokes mid-conversation (`06_contract_and_safety.md` §1).

---

## 6. Document index

| Doc | Contents |
|---|---|
| [`01_architecture.md`](01_architecture.md) | Component diagram, dependency graph, package layout, request lifecycle, degradation policy, concurrency model |
| [`02_api_spec.md`](02_api_spec.md) | Every data model and the full contract (params/returns/errors) for `ContextManagerPort` and `ConversationManagerPort` |
| [`03_context_composition.md`](03_context_composition.md) | Context Manager internals: Requirement Analyzer, Retrieval Planner, Aggregator, Ranker, Compressor, Validator, Cache |
| [`04_conversation_memory.md`](04_conversation_memory.md) | Conversation Manager internals: Message Store, Summarizer, Decision Extractor, Memory Index, Retriever, storage layout |
| [`05_execution_context.md`](05_execution_context.md) | ExecutionContext structure, ownership matrix, lifecycle, immutable functional-update API, reconciliation with the pre-existing `ExecutionContext` schema |
| [`06_contract_and_safety.md`](06_contract_and_safety.md) | How agents consume these ports, safety invariants, cache reuse, observability, testing strategy |
| [`07_implementation_plan.md`](07_implementation_plan.md) | Phase-by-phase build plan: order, deliverables, acceptance criteria, tests, risks |
