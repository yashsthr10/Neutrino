# Low-level design (LLD)

Key modules, entrypoints, and types. For full method indexes, use package READMEs.

## Entrypoints

| Entry | Module | Role |
|-------|--------|------|
| `neutrino` CLI | [`src/entry.py`](../src/entry.py) | Spawns Ink TUI (Node) against Python RPC |
| `python -m src.rpc` | [`src/rpc/__main__.py`](../src/rpc/__main__.py) | NDJSON server process |
| `python -m src.agent` | [`src/agent/cli.py`](../src/agent/cli.py) | Headless agent loop |
| `rna` CLI / MCP | [`src/rna/cli.py`](../src/rna/cli.py) | Standalone RNA / `rna serve` |
| `neutrino-auth` | credentials CLI | List/set/remove provider secrets |

## Control path (modules)

```text
src/rpc/server.py
  └─ AgentOrchestrator          src/orchestrator/agent_orchestrator.py
        ├─ env_probe            src/orchestrator/env_probe.py
        ├─ WorkflowController   src/orchestrator/workflow.py
        ├─ CompletionPolicy     src/orchestrator/completion.py
        └─ AgentController      src/agent/controller.py
              └─ AgentLoop      src/agent/loop.py
                    ├─ compile_system_prompt   src/agent/prompts/compiler.py
                    ├─ InferencePort.chat      src/inference/
                    ├─ ToolEngine.invoke       src/tool_engine/engine.py
                    ├─ derive_agent_state      src/agent/state_model.py
                    └─ reminders               src/agent/reminders.py
```

### Tool Engine internals

```text
ToolEngine.invoke
  → Registry + state_policy gate
  → Validator (args vs ToolSpec)
  → Dispatcher → Capability handler
  → Executor (timing / events)
  → Serializer → ToolResult
```

Capabilities live under `src/tool_engine/capabilities/`; intention names under `src/tool_engine/tools/`.

## Core types

| Type | Location | Role |
|------|----------|------|
| `ExecutionContext` | `src/context/runtime/` | Immutable, ownership-partitioned run state |
| `ToolSpec` / `ToolRequest` / `ToolResult` | `src/tool_engine/models.py` | Catalog entry, call, LLM-facing result |
| `AgentState` | `src/agent/state_model.py` | Soft phase + objectives for prompt L5 |
| `CompiledPrompt` / `PromptInputs` | `src/agent/prompts/compiler.py` | L1–L6 assembly inputs/output |
| `UIEvent` union | `src/ports/orchestrator_port.py` | Runtime → presentation notifications |
| `OrchestratorPort` | `src/ports/orchestrator_port.py` | Commands the UI may send |
| `InferencePort` | `src/inference/ports/` | Chat / stream abstraction |
| `RnaResult[T]` | `src/rna/` | Bounded RNA answers + meta |
| `ContextPackage` | `src/context/` | Ranked, budgeted retrieval package |
| `VerificationPolicy` | `src/verification/harness.py` | `checks_required` / waive reasons |

## Prompt compiler layers

| Layer | Module | Content |
|-------|--------|---------|
| L1 | `prompts/layers/core.py` | Identity + response contract |
| L2 | `prompts/layers/capabilities.py` | Tools from live `ToolSpec`s |
| — | `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` | Cache-friendly split |
| L3 | `prompts/layers/environment.py` | cwd, git, harness |
| L4 | `prompts/layers/task_context.py` | User task, working set, verify policy |
| L5 | `prompts/layers/agent_state.py` | Soft phase |
| L6 | `reminders.py` | Ephemeral `<system-reminder>` user message |

## Important call conventions

- Agent always invokes tools with `state="AGENT"` (legacy phase labels are aliases of the same allowlist).
- `executor.run` requires `approved=true` after host/TUI confirmation.
- Soft failures return `ToolResult.success=False` + `meta.error` — they rarely raise.
- Orchestrator may `continue_phase` with the **same** message history when CompletionPolicy returns CONTINUE.

## Related

- [Architecture](01_architecture.md)  
- [Patterns](05_patterns.md)  
- Agent README: [`src/agent/README.md`](../src/agent/README.md)  
- Orchestrator README: [`src/orchestrator/README.md`](../src/orchestrator/README.md)  
