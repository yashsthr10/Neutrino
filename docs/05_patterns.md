# Patterns

Recurring implementation patterns across Neutrino. Prefer extending these over inventing parallels.

## 1. Port + Fake

Define a `Protocol` at the boundary; ship a deterministic fake for tests and offline runs.

| Port | Fake / stand-in |
|------|-----------------|
| `OrchestratorPort` | `src/orchestrator/fake.py`, `src/rpc/dummy.py` |
| `InferencePort` | Fake provider under `src/inference/` |
| `RnaPort` | `src/rna/fake.py` |
| Context / Conversation ports | Fakes under `src/context/` |

**Rule:** Host tests should not require live LLMs, LSPs, or network.

## 2. Capability layer over services

Tool Engine does not embed domain algorithms. It validates and dispatches to capability handlers that call injected ports (`RuntimeServices`).

```text
ToolSpec.handler_key → Dispatcher → Capability method → Service port
```

## 3. ToolSpec as single behavioral source

Each tool carries `description`, `when_to_use`, `when_not_to_use`, `pairs_with`, `parameters`.

- Provider schemas: `enrich_tool_description` in `src/tool_engine/contracts/schema.py`  
- Prompt L2: `render_capabilities` in `src/agent/prompts/layers/capabilities.py`  

Do not hardcode parallel tool lists in prompts.

## 4. Immutable partitioned `ExecutionContext`

Run state is an immutable aggregate of sub-contexts (request, repository, conversation, planning, execution, verification, metrics, events). Updates return a new context (`with_*`). One legitimate writer per partition — see Context docs.

## 5. Layered prompts with a cache boundary

```text
L1 + L2  |  __SYSTEM_PROMPT_DYNAMIC_BOUNDARY__  |  L3 + L4 + L5
(static-ish)                                      (per-turn dynamic)
+ L6 reminders as request-local user messages (not persisted)
```

Keeps identity/capability text stable while env/task/state change every turn.

## 6. Soft state derived from evidence

`derive_agent_state(...)` updates phase/objectives from tool outcomes (`apply_succeeded`, verification failure, plan tasks, …). Advisory only — CompletionPolicy still owns finish.

## 7. Approval-gated dangerous tools

`executor.run` requires explicit approval (`approved=true`) after TUI/host confirm. Pattern: tool returns `needs_approval` / `WAITING_USER` → UI approve → resume with same request id.

## 8. Event stream UI

Runtime emits typed `UIEvent`s → RPC mapper → `ui.event` notifications → TUI reducer → transcript. No shared mutable UI store inside Python domain code.

## 9. Soft errors in results

RNA (`RnaResult.meta.error`) and Tool Engine (`ToolResult.meta.error`) prefer structured soft failure over exceptions for “not found”, validation, not implemented. Reserve exceptions for invariant / security breaks.

## 10. State-gated catalogs with aliases

`state_policy.allowed_tools("AGENT")` is the productive surface. Legacy labels (`PLAN`, `EXECUTE`, …) alias the same allowlist during migration — avoid reintroducing hard phase gates in the tool layer.

## Related

- [LLD](03_lld.md)  
- [Design](04_design.md)  
- Tool Engine README: [`src/tool_engine/README.md`](../src/tool_engine/README.md)  
