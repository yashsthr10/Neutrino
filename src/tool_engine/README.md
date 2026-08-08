# Tool Engine — LLM capabilities over the Neutrino Runtime

Execution bridge between language models and runtime services. It **validates, dispatches, executes, and serializes** tool calls. It does **not** contain repository analysis, planning, git, or verification logic — those stay in Context, RNA, and future services behind a Capability Layer.

```text
Tool Engine
├── ToolEngine             — schemas_for_state / list_tools / invoke
├── Registry + Validator   — catalog, enablement, state gates, arg checks
├── Dispatcher + Executor  — route → capability handler, timed execution
├── Serializer             — LLM-friendly ToolResult payloads
└── Capability Layer       — intention tools → ContextManagerPort / RnaPort / stubs
```

- **Library:** `from src.tool_engine import ToolEngine, build_tool_engine, ToolRequest, ToolResult`
- **Fakes (tests):** inject `FakeContextManager`, `FakeConversationManager`, `FakeRna` via `RuntimeServices`
- Deeper design notes live in [`docs/`](docs/).

Unlike RNA MCP (`rna_get_*`), this is the **agent/runtime** tool surface: intention names (`context.resolve`, `rna.find_symbol`), state-aware catalogs, and a single `invoke` path.

---

## Install

From the NeutrinoCLI repo root (same package as RNA / Context):

```bash
pip install -e .
```

Verify:

```bash
python -c "from src.tool_engine import build_tool_engine; print('ok')"
```

---

## Quick start (library)

Prefer `build_tool_engine(...)` with injected ports — the canonical wiring path:

```python
from src.context.fake import FakeContextManager, FakeConversationManager
from src.rna.fake import FakeRna
from src.tool_engine import RuntimeServices, ToolRequest, build_tool_engine

engine = build_tool_engine(
    RuntimeServices(
        context=FakeContextManager(),
        conversation=FakeConversationManager(),
        rna=FakeRna(),
    )
)

# What the LLM may call in PLAN
schemas = engine.schemas_for_state("PLAN")

result = engine.invoke(
    ToolRequest(
        name="context.resolve",
        arguments={
            "task_description": "add caching to pkg/parser.py",
            "task_complexity": "MEDIUM",
            "requesting_agent": "planner",
            "file_hints": ["pkg/parser.py"],
        },
    ),
    state="PLAN",
)

print(result.success)
print(result.data)           # compact LLM view (not raw ContextPackage)
print(result.meta.error)     # None | "validation_error" | "not_implemented" | ...
print(result.to_dict())
```

Wire real Context + RNA in one shot:

```python
from pathlib import Path
from src.rna import Rna, RnaConfig
from src.tool_engine import build_tool_engine_from_subsystem

repo = Path("/path/to/your/repo").resolve()
rna = Rna(RnaConfig(repo_path=repo))
engine = build_tool_engine_from_subsystem(
    rna,
    session_id="session-123",
    repo_path=repo,
)
```

---

## Common return shape

Every `invoke` returns `ToolResult` (errors are soft — callers rarely catch):

| Field | Type | Meaning |
|---|---|---|
| `success` | `bool` | Handler completed without engine/capability hard failure |
| `data` | `Any` | LLM-facing payload (dict / nested JSON-serializable) |
| `meta.cost_ms` | `float` | Wall time for the call |
| `meta.truncated` | `bool` | Payload capped for size |
| `meta.degraded` | `bool` | Downstream Context/RNA reported degrade |
| `meta.reason` | `str \| None` | Why degraded / extra context |
| `meta.error` | `str \| None` | Soft error code (see below) |
| `meta.result_bytes` | `int` | Serialized payload size hint |
| `meta.tool_version` | `str` | Spec version string |
| `errors` | `tuple[str, ...]` | Human-readable failure messages |

```python
result.to_dict()  # {"success", "data", "meta", "errors"}
```

**Soft `meta.error` codes:** `tool_not_found`, `tool_disabled`, `permission_denied`, `validation_error`, `execution_error`, `not_implemented`, `disabled`, …

**Exceptions (rare, internal):** `ToolNotFound`, `ValidationError`, `PermissionDenied`, `ExecutionError` — mapped to `ToolResult` at the engine boundary.

---

## Method index

### ToolEngine

| Method | One-line purpose |
|---|---|
| [`schemas_for_state`](#1-schemas_for_state) | OpenAI/Anthropic-style function schemas for the current FSM state |
| [`list_tools`](#2-list_tools) | `ToolSpec` list filtered by state |
| [`invoke`](#3-invoke) | Validate → dispatch → execute → serialize one tool call |

Helpers: [`build_tool_engine`](#helpers), [`build_tool_engine_from_subsystem`](#helpers).

### Intention tools (LLM names)

#### Context

| Tool | Backend | Status |
|---|---|---|
| [`context.resolve`](#4-contextresolve) | `ContextManagerPort.resolve` | Live |
| [`context.expand`](#5-contextexpand) | `ContextManagerPort.expand` | Live |
| [`context.refresh`](#6-contextrefresh) | invalidate + resolve | Live |

#### Repository (RNA)

| Tool | Backend | Status |
|---|---|---|
| [`rna.find_symbol`](#7-rnafind_symbol) | `RnaPort.get_symbol` | Live |
| [`rna.trace_workflow`](#8-rnatrace_workflow) | `RnaPort.get_workflow` | Live |
| [`rna.find_tests`](#9-rnafind_tests) | `RnaPort.get_tests` | Live |
| [`rna.find_related`](#10-rnafind_related) | compose callers + tests + import graph | Live |
| [`rna.semantic_search`](#11-rnasemantic_search) | `RnaPort.semantic_search` | Live |

#### Research

| Tool | Backend | Status |
|---|---|---|
| [`research.web`](#12-researchweb) | `RnaPort.google_search` | Live |
| [`research.docs`](#13-researchdocs) | — | Stub (`not_implemented`) |

#### Execution / Verification / Git (Phase A stubs)

| Tool | Status |
|---|---|
| [`executor.apply`](#14-stubs) / `executor.rollback` / `executor.diff` | Stub |
| [`tests.run`](#14-stubs) / `lint.run` / `review.run` | Stub |
| [`git.commit`](#14-stubs) / `git.undo` / `git.diff` | Stub |

---

## State-aware catalog

Only tools allowed for the current FSM phase are exposed via `schemas_for_state` / accepted by `invoke`.

| State | Available |
|---|---|
| `PLAN` / `CONTEXT` | `context.*`, `rna.*`, `research.*`, `plan.set_tasks` |
| `EXECUTE` | `context.refresh`, `context.resolve`, `rna.*`, `executor.*`, `git.*`, `tests.run`, `plan.set_tasks` |
| `VERIFY` / `REVIEW` | `tests.run`, `lint.run`, `review.run`, `context.refresh`, `rna.find_tests`, `plan.set_tasks` |
| `INIT` / `DONE` / `CANCELLED` | none |

`plan.set_tasks` tracks a todo checklist across phases (see `PlanningContext.tasks`). It is
informational bookkeeping only — it never gates FSM transitions; `WorkflowController` remains
the sole authority for phase changes, including the bounded `VERIFY -> EXECUTE` retry when
verification fails (`WorkflowController.max_verify_cycles`).

Pass `state=` on every `invoke` (orchestrator owns the FSM). `ExecutionContext` is an optional input for future inference; the engine never mutates it.

---

## 1. `schemas_for_state`

Return function schemas the LLM may call in this state.

### Signature

```python
schemas_for_state(state: str) -> list[dict]
```

### Output

List of objects shaped like:

```python
{
  "name": "context.resolve",
  "description": "...",
  "parameters": {
    "type": "object",
    "properties": {...},
    "required": [...],
    "additionalProperties": False,
  },
}
```

### Usage

```python
for schema in engine.schemas_for_state("PLAN"):
    print(schema["name"])
# context.expand, context.refresh, context.resolve, rna.*, research.*
assert "executor.apply" not in {s["name"] for s in engine.schemas_for_state("PLAN")}
```

---

## 2. `list_tools`

Same filter as schemas, but returns `ToolSpec` objects (name, parameters, category, states, version).

### Signature

```python
list_tools(state: str) -> list[ToolSpec]
```

---

## 3. `invoke`

Full pipeline: state gate → validate args → capability handler → serialize → `ToolResult`.

### Signature

```python
invoke(request: ToolRequest, *, state: str | None = None) -> ToolResult
```

### Input

| Param | Required | Description |
|---|---|---|
| `request.name` | yes | Intention tool name, e.g. `"rna.find_symbol"` |
| `request.arguments` | no | JSON-object args matching the tool schema |
| `request.execution_context` | no | Opaque runtime snapshot (not mutated) |
| `state` | recommended | FSM phase; defaults to `INIT` if omitted |

### Usage

```python
r = engine.invoke(
    ToolRequest("rna.find_symbol", {"name": "parse_request", "file_hint": "pkg/parser.py"}),
    state="PLAN",
)
if r.success:
    print(r.data["data"])  # list of SymbolRef dicts (RnaResult shape)
else:
    print(r.meta.error, r.errors)
```

---

## 4. `context.resolve`

Build a bounded context package for the current task. Capability → `ContextManagerPort.resolve`.

### Arguments

| Param | Required | Description |
|---|---|---|
| `task_description` | yes | User task / goal |
| `task_complexity` | no | `SIMPLE` \| `MEDIUM` \| `COMPLEX` (default `MEDIUM`) |
| `requesting_agent` | no | `planner` \| `coder` \| `verifier` \| `reviewer` (default `planner`) |
| `file_hints` | no | Optional file path hints |
| `symbol_hints` | no | Optional symbol name hints |
| `conversation_query` | no | Optional memory query |
| `token_budget` | no | Optional token budget override |
| `session_id` | no | Optional session id |

### Output (`data`)

Compact LLM view (not the full internal `ContextPackage` graph):

| Field | Description |
|---|---|
| `task_description` | Echo |
| `repository.items` | Top ranked items (payloads may truncate large `content`) |
| `conversation.recent_messages` | Short recent slice |
| `tokens_estimate` / `token_budget` / `truncated` / `provenance` | Budgeting metadata |

States: `PLAN`, `CONTEXT`.

---

## 5. `context.expand`

Widen context with an additional retrieval goal. Capability → resolve/expand path on `ContextManagerPort`.

### Arguments

Same core fields as [`context.resolve`](#4-contextresolve), plus optional `package` (prior package summary dict). Without a live host-held `ContextPackage`, the capability safely re-resolves then expands.

States: `PLAN`, `CONTEXT`.

---

## 6. `context.refresh`

Invalidate cache and re-resolve after repo changes. Capability → `invalidate` + `resolve`.

### Arguments

| Param | Required | Description |
|---|---|---|
| `task_description` | no | Defaults to `"refresh context"` |
| `file_hints` / `symbol_hints` / … | no | Same as resolve |

States: `PLAN`, `CONTEXT`, `EXECUTE`, `VERIFY`, `REVIEW`.

---

## 7. `rna.find_symbol`

Go-to-definition. Maps to `RnaPort.get_symbol`.

### Arguments

| Param | Required | Description |
|---|---|---|
| `name` | yes | Symbol name |
| `file_hint` | no | Optional file path hint |

### Output (`data`)

Serialized `RnaResult` dict: `{"data": [...SymbolRef...], "meta": {...}}`.

States: `PLAN`, `CONTEXT`, `EXECUTE`.

---

## 8. `rna.trace_workflow`

Trace a call path from an entrypoint. Maps to `RnaPort.get_workflow`.

### Arguments

| Param | Required | Description |
|---|---|---|
| `entrypoint` | yes | Entrypoint symbol or path |
| `max_depth` | no | Max traversal depth (default `4`) |

States: `PLAN`, `CONTEXT`, `EXECUTE`.

---

## 9. `rna.find_tests`

Find tests related to a target. Maps to `RnaPort.get_tests`.

### Arguments

| Param | Required | Description |
|---|---|---|
| `target` | yes | Symbol or module target |

States: `PLAN`, `CONTEXT`, `EXECUTE`, `VERIFY`, `REVIEW`.

---

## 10. `rna.find_related`

Compose related facts (no dedicated RNA method): `get_callers` + `get_tests` + `get_import_graph`.

### Arguments

| Param | Required | Description |
|---|---|---|
| `symbol` | yes | Symbol name |
| `file_hint` | no | Optional file/module scope |
| `limit` | no | Caller limit (default `25`) |

### Output (`data`)

```python
{
  "data": {
    "symbol": "...",
    "callers": <RnaResult.to_dict()>,
    "tests": <RnaResult.to_dict()>,
    "imports": <RnaResult.to_dict()>,
  },
  "meta": {...},
}
```

States: `PLAN`, `CONTEXT`, `EXECUTE`.

---

## 11. `rna.semantic_search`

Meaning-based code search. Maps to `RnaPort.semantic_search`.

### Arguments

| Param | Required | Description |
|---|---|---|
| `query` | yes | Natural-language query |
| `limit` | no | Max hits (default `10`) |

States: `PLAN`, `CONTEXT`, `EXECUTE`.

---

## 12. `research.web`

External web search. Maps to `RnaPort.google_search` (may soft-fail with `meta.error="disabled"` if web is off).

### Arguments

| Param | Required | Description |
|---|---|---|
| `query` | yes | Search query |
| `limit` | no | Max results (default `5`) |

States: `PLAN`, `CONTEXT`.

---

## 13. `research.docs`

Project/docs index — **not implemented** in Phase A. Returns `success=False`, `meta.error="not_implemented"`.

States: `PLAN`, `CONTEXT`.

---

## 14. Stubs

`executor.*`, `tests.run`, `lint.run`, `review.run`, `git.*` register schemas and honor state gates, but handlers return:

```python
ToolResult(
  success=False,
  data={"tool": "<name>", "status": "not_implemented"},
  meta=ToolMeta(error="not_implemented", reason="Service not wired in Phase A"),
  errors=("not_implemented",),
)
```

Tool names stay stable when real services land.

---

## Helpers

### `build_tool_engine`

```python
build_tool_engine(services: RuntimeServices, *, on_event=None) -> ToolEngine
```

Registers all `ToolSpec`s, binds capability handlers, returns a ready engine. Optional `on_event(event_name, payload)` for orchestrator hooks (`ToolStarted` / `ToolCompleted` / `ToolFailed`).

### `build_tool_engine_from_subsystem`

```python
build_tool_engine_from_subsystem(
    rna,
    session_id: str,
    *,
    config: ContextConfig | None = None,
    repo_path: Path | None = None,
    on_event=None,
) -> ToolEngine
```

Calls `build_context_subsystem(...)` then `build_tool_engine(RuntimeServices(...))`.

### `RuntimeServices`

```python
@dataclass
class RuntimeServices:
    context: ContextManagerPort | None = None
    conversation: ConversationManagerPort | None = None
    rna: RnaPort | None = None
```

The LLM never receives this object. Capabilities are the only callers.

---

## Models

### `ToolRequest`

| Field | Type | Description |
|---|---|---|
| `name` | `str` | Intention tool name |
| `arguments` | `dict` | JSON-object args |
| `execution_context` | `ExecutionContext \| None` | Optional runtime snapshot |

### `ToolSpec`

| Field | Type | Description |
|---|---|---|
| `name` | `str` | LLM-facing name |
| `description` | `str` | Schema description |
| `parameters` | `tuple[ToolParam, ...]` | Arg schema |
| `category` | `str` | `context` / `rna` / `research` / … |
| `handler_key` | `str` | Capability dispatch key (equals `name` in Phase A) |
| `states` | `frozenset[str]` | FSM phases where the tool may appear |
| `version` | `str` | Spec version |

---

## Package layout

```text
tool_engine/
├── engine.py
├── registry.py
├── validator.py
├── dispatcher.py
├── executor.py
├── serializer.py
├── errors.py
├── models.py
├── observability.py
├── state_policy.py
├── capabilities/          # Context / RNA / Research / stubs
├── tools/                 # ToolSpec registrations
└── contracts/schema.py    # JSON-schema export
```

---

## Non-goals (Phase A)

- Wiring into Ink TUI / RPC dummy / real orchestrator
- Replacing RNA MCP (`rna_get_*` stays a separate surface)
- Real git write, patch apply, or test runners
- Changing Context Manager or RNA public ports

Callers that own `ExecutionContext` should append `ToolResult.to_dict()` into `ExecutionState.tool_results` after `invoke` — the engine never mutates runtime state.
