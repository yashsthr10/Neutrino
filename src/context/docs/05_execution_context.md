# ExecutionContext — Runtime State

`ExecutionContext` is not a manager. It has no methods that compute anything. It is the single, complete runtime state snapshot of one execution — think Kubernetes' object model, a Temporal workflow's state, or an OS process's memory image: something every stage reads, and into which exactly one stage at a time writes exactly its own slice.

---

## 1. Structure

```python
@dataclass(frozen=True, slots=True)
class ExecutionContext:
    request: RequestContext
    repository: RepositoryContext | None = None
    conversation: ConversationContext | None = None
    planning: PlanningContext = field(default_factory=PlanningContext)
    execution: ExecutionState = field(default_factory=ExecutionState)
    verification: VerificationContext = field(default_factory=VerificationContext)
    metrics: MetricsContext = field(default_factory=MetricsContext)
    events: EventLog = field(default_factory=EventLog)
    version: int = 0
```

Sub-contexts:

```python
@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    session_id: str
    user_query: str
    repo_path: str
    requesting_agent: RequestingAgent
    task_complexity: TaskComplexity
    created_at: str

@dataclass(frozen=True, slots=True)
class PlanningContext:
    plan_steps: tuple[str, ...] = ()
    current_step: int = 0

@dataclass(frozen=True, slots=True)
class ExecutionState:
    code_changes: tuple[dict, ...] = ()     # diffs/patches -- opaque to the Context Subsystem
    tool_results: tuple[dict, ...] = ()
    iteration_count: int = 0
    status: Literal["INIT", "RUNNING", "DONE", "FAIL"] = "INIT"

@dataclass(frozen=True, slots=True)
class VerificationContext:
    test_results: dict | None = None
    reviewer_feedback: dict | None = None

@dataclass(frozen=True, slots=True)
class MetricsContext:
    token_usage_used: int = 0
    token_usage_budget: int | None = None
    cost_ms_by_stage: dict[str, float] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    payload: dict
    at: str

@dataclass(frozen=True, slots=True)
class EventLog:
    events: tuple[Event, ...] = ()
```

`RepositoryContext` and `ConversationContext` are the exact same types the Context Manager returns inside a `ContextPackage` — defined once, in `runtime/repository_context.py` and `runtime/conversation_context.py` (`01_architecture.md` §3.1). `code_changes` and `tool_results` are stored as opaque `dict`s here deliberately: their schema belongs to the Tool Layer and Executor, which this design set is not redefining (per the user's own scoping: this document only covers the Context Subsystem).

---

## 2. Immutability and the functional-update API

`ExecutionContext` is frozen. There is no setter for any field. The only way to change it is:

```python
class ExecutionContext:
    def with_repository(self, repository: RepositoryContext) -> ExecutionContext: ...
    def with_conversation(self, conversation: ConversationContext) -> ExecutionContext: ...
    def with_planning(self, planning: PlanningContext) -> ExecutionContext: ...
    def with_execution(self, execution: ExecutionState) -> ExecutionContext: ...
    def with_verification(self, verification: VerificationContext) -> ExecutionContext: ...
    def with_metrics(self, metrics: MetricsContext) -> ExecutionContext: ...
    def with_event(self, kind: str, payload: dict) -> ExecutionContext: ...
```

Each `with_*` returns a **new** `ExecutionContext` with `version = self.version + 1` and every other field copied unchanged. The orchestrator holds exactly one live reference and reassigns it:

```python
ctx = ctx.with_planning(PlanningContext(plan_steps=steps, current_step=0))
...
ctx = ctx.with_execution(ctx.execution.__class__(..., iteration_count=ctx.execution.iteration_count + 1))
```

This is the actual enforcement mechanism behind "nobody owns everything" — not a convention documented in a comment, but a type-level guarantee: there is no code path by which the Verifier can accidentally write `planning`, because nothing in `ExecutionContext`'s public surface lets *any* caller touch a field other than through the `with_*` method for the section it legitimately owns. (Nothing stops a determined caller from calling `ctx.with_planning(...)` from the wrong module today — that boundary is enforced by module-level convention, the same way RNA's read-only guarantee is enforced by never exposing a write method rather than by a runtime permission check. A future refinement could split write-capability by issuing each stage a narrower `Writer` object that only exposes the one `with_*` it's entitled to; not required for this design to be internally consistent.)

This gives three properties for free, without any additional code:

1. **Trivial checkpointing.** A checkpoint *is* a reference to a specific `ExecutionContext` version. Keeping the last N versions (or persisting each one) is exactly as cheap as keeping N object references, because nothing is ever mutated in place.
2. **Trivial concurrency safety.** A concurrent reader (a TUI status projection, a logger, a background checkpoint writer) can hold a reference to any past version and it will never change underneath it. No locks are needed to read an `ExecutionContext`.
3. **Trivial serialization.** `to_dict()` is a pure `asdict()`-style walk, identical in spirit to `RnaResult.to_dict()` — there is never a "the object changed while I was serializing it" race.

---

## 3. Ownership matrix

| Sub-context | Written by | Read by |
|---|---|---|
| `request` | Orchestrator, once, at creation — never updated after | Everyone |
| `repository` | **Context Manager only** (via `ContextPackage.repository`) | Planner, Coder, Verifier, Reviewer |
| `conversation` | **Context Manager only** (via `ContextPackage.conversation`) | Planner, Coder, Verifier, Reviewer |
| `planning` | Planner only | Executor, Verifier, Reviewer, Context Manager (as a `ContextRequest` input signal) |
| `execution` | Executor only | Verifier, Reviewer, Context Manager (`code_changes` feeds `verifier`'s `file_hints`, `03_context_composition.md` §2) |
| `verification` | Verifier only | Reviewer, Orchestrator (gating decision) |
| `metrics` | Whichever stage just ran, for its own cost/token contribution | Orchestrator (budget enforcement), TUI (`StatusSnapshot`) |
| `events` | Every stage appends its own events; nobody removes any | Observability/logging, TUI, checkpoint/audit tooling |

No sub-context has more than one legitimate writer. This is the same one-writer-per-slice discipline the Conversation Manager applies to its own message store (`04_conversation_memory.md` §1), just applied at the whole-execution scope instead of the whole-session scope.

---

## 4. Lifecycle

```text
Created
   │  Orchestrator builds RequestContext from the incoming task, wraps it in a fresh
   │  ExecutionContext (version=0), all other sub-contexts at their defaults.
   ▼
Updated
   │  Each stage that runs calls exactly one with_*(), producing the next version.
   │  Repeated for every stage of every iteration (Context Manager resolves context for a
   │  step, Planner plans, Executor executes, Verifier verifies, Reviewer reviews, repeat).
   ▼
Checkpointed
   │  After each FSM state transition (docs/02_specs.md S5), the orchestrator persists the
   │  current version (to.dict()) to Neutrino Manager's Execution History -- out of scope for
   │  this design set, but the hook is exactly "hand the orchestrator's current ExecutionContext
   │  reference to whatever the durable store is."  A crash/retry resumes from the last
   │  checkpointed version, not from scratch.
   ▼
Serialized
   │  On demand (checkpointing, telemetry export, TUI ContextSummary/StatusSnapshot
   │  projections) via to_dict() -- pure, side-effect-free, safe to call from any thread
   │  holding a reference to any version.
   ▼
Destroyed
      On DONE/FAIL (docs/02_specs.md S5), the orchestrator drops its reference. Nothing in the
      Context Subsystem needs an explicit teardown call -- there is no open resource (file
      handle, connection, subprocess) owned by ExecutionContext itself; only Context Manager's
      and Conversation Manager's own caches/stores have lifetimes, and those are scoped to the
      session/process, not to one ExecutionContext instance.
```

---

## 5. Reconciliation with the existing `ExecutionContext` schema

`docs/02_specs.md` §2 already fixes a strict `ExecutionContext` schema as a system-wide invariant, predating this design. Every field in that schema has exactly one new home below — nothing is dropped, nothing is redefined incompatibly, and the "single source of truth" and "context must be bounded" invariants from that document (`docs/02_specs.md` §2, §8) still hold, now enforced per-slice instead of on one flat object.

| Old field (`docs/02_specs.md` §2) | New home | Notes |
|---|---|---|
| `user_query` | `RequestContext.user_query` | |
| `repo_path` | `RequestContext.repo_path` | |
| `repo_tree` | `RepositoryContext` (items of `kind="file"`/repo-tree-derived items) | Previously a raw tree object; now a bounded, ranked, cached `RepositoryContext` produced by the Context Manager instead of a full unbounded tree dump |
| `dependency_graph` | `RepositoryContext` (items of `kind="import_edge"`) | Previously a whole-repo graph; now scoped to what Requirement Analysis actually planned for the current task |
| `task_complexity` | `RequestContext.task_complexity` | Same enum, same values, same source of truth (`02_api_spec.md` §2) |
| `plan_steps` | `PlanningContext.plan_steps` | |
| `current_step` | `PlanningContext.current_step` | |
| `code_changes` | `ExecutionState.code_changes` | |
| `tool_results` | `ExecutionState.tool_results` | |
| `test_results` | `VerificationContext.test_results` | |
| `reviewer_feedback` | `VerificationContext.reviewer_feedback` | |
| `token_usage` | `MetricsContext.token_usage_used` / `token_usage_budget` | Split into used/budget as two fields instead of one dict, matching `RnaMeta`/`ContextMeta`'s own `tokens_estimate` convention |
| `iteration_count` | `ExecutionState.iteration_count` | |
| `status` | `ExecutionState.status` | Same `{INIT, RUNNING, DONE, FAIL}` enum |

New, not present in the old flat schema:

- **`ConversationContext`** — conversational memory did not previously have a first-class home in `ExecutionContext` at all; it now does, owned by the Context Manager the same way `RepositoryContext` is.
- **`EventLog`** — an explicit, append-only, structured trace of what happened during this execution, satisfying `docs/02_specs.md` §8's "Logs must exist for every state" as a queryable object rather than only as text log lines.
- **`MetricsContext.cost_ms_by_stage`** — per-stage cost breakdown, feeding the same observability posture RNA already applies per-call (`rna/docs/05_tool_contract_and_safety.md` §4) up to the whole-execution level.

The old schema's constraint *"Must be the single source of truth"* is preserved exactly: there is still exactly one `ExecutionContext` per execution, and every stage still reads from and writes to it — the only change is that "the single source of truth" is now a composed, ownership-partitioned object instead of one flat mutable bag, which is what makes "nobody owns everything" possible without weakening "single source of truth" at all.

---

## 6. Relationship to existing TUI-facing snapshots

`src/ports/orchestrator_port.py` already defines `StatusSnapshot` (`mode_label`, `tokens_used`, `fsm_state`, `task_complexity`) and `ContextSummary` (`files`, `edges`, `tokens_used`, `token_budget`) as immutable events pushed to the TUI. Under this design, both are pure projections of one `ExecutionContext` version — `StatusSnapshot` reads `metrics` + `execution.status` + `request.task_complexity`; `ContextSummary` reads `repository.items` (filtered to `kind="file"`/`"import_edge"`) + `metrics.token_usage_*`. Neither snapshot needs to become a second source of truth; they are derivable, on demand, from whatever `ExecutionContext` version the orchestrator currently holds. This note exists only to confirm consistency with an already-defined contract elsewhere in the codebase — the TUI/orchestrator wiring itself is out of scope for this design set, per its own stated focus on the Context Subsystem alone.
