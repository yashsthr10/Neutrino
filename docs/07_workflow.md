# Workflow / codeflow

End-to-end path from a user task to DONE (or BLOCKED), including soft phases and approvals.

## Happy path (sequence)

```mermaid
sequenceDiagram
  participant User
  participant TUI
  participant RPC
  participant Orch as Orchestrator
  participant Loop as AgentLoop
  participant Infer as Inference
  participant Tools as ToolEngine
  participant Svc as DomainServices

  User->>TUI: submit_task
  TUI->>RPC: runtime.execute
  RPC->>Orch: submit_task
  Orch->>Orch: build_ExecutionContext_probe_env
  Orch->>Loop: run_fsm_AGENT
  loop until_final_or_wait
    Loop->>Loop: compile_L1_L6_prompt
    Loop->>Infer: chat_with_tool_schemas
    Infer-->>Loop: tool_calls_or_final
    alt tool_calls
      Loop->>Tools: invoke
      Tools->>Svc: capability_handlers
      Svc-->>Tools: results
      Tools-->>Loop: ToolResult
      Loop->>Orch: fold_side_effects_emit_UIEvent
      Orch-->>TUI: ui.event
    else final_message
      Loop-->>Orch: AgentResult_COMPLETED
      Orch->>Orch: evaluate_completion
    end
  end
  alt DONE
    Orch-->>TUI: RunFinished_ok
  else CONTINUE
    Orch->>Loop: continue_phase_same_history
  else BLOCKED
    Orch-->>TUI: RunFinished_fail
  end
```

## Hard workflow status vs soft phase

| Layer | Values | Who updates |
|-------|--------|-------------|
| Hard status (`WorkflowController`) | `INIT` → `AGENT` → `DONE` / `CANCELLED` | Orchestrator |
| Soft phase (`AgentState`, prompt L5) | `DISCOVER` → `PLAN` → `IMPLEMENT` → `VERIFY` → `REPAIR` → `DONE` | `derive_agent_state` from tool evidence |
| UI `fsmState` | Often shows soft phase while hard status is still `AGENT` | TUI / mapper |

Do not treat soft phase transitions as completion gates.

## Orchestrator run lifecycle

1. Build `ExecutionContext` (`fast`→SIMPLE / `deep`→COMPLEX).  
2. `probe_environment` → seed verification policy + L3 snapshot.  
3. `WorkflowController.start()` → `AGENT`.  
4. `AgentController.run(..., fsm_state="AGENT")`.  
5. On model final → `evaluate_completion`:
   - **DONE** → mark workflow DONE, `RunFinished(ok=True)`  
   - **CONTINUE** → pending L6 nudge, `continue_phase` (same history)  
   - **BLOCKED** → `RunFinished(ok=False)`  
6. On `WAITING_USER` (shell approval) → TUI approve/reject → resume.

Details: [`src/orchestrator/README.md`](../src/orchestrator/README.md).

## Agent loop (one iteration)

1. Compile system prompt (`PromptInputs` include tools, env, task, agent state).  
2. Attach ephemeral L6 reminder message if any.  
3. `InferencePort.chat` with `schemas_for_state("AGENT")`.  
4. Classify → tool calls / final / invalid / error.  
5. For each tool: policy guards → optional approval → `ToolEngine.invoke`.  
6. Update reminder facts + soft `AgentState`.  
7. Emit timing / tool events upward.

Details: [`src/agent/README.md`](../src/agent/README.md).

## Approval subflow (`executor.run`)

```text
Model calls executor.run(approved=false)
  → AgentLoop detects needs_approval
  → AgentResult WAITING_USER + ApprovalRequest UIEvent
  → User Approve / Reject in TUI
  → runtime.approve
  → Loop resumes with approved=true (or cancels)
```

## Context folding

Successful `context.resolve` / `expand` / `refresh` project into `ExecutionContext.repository` and `.conversation` so L4 can show a working set without re-parsing raw tool JSON every turn.

## Headless path

```bash
python -m src.agent --repo . "your task"
```

Same AgentLoop + Tool Engine; no TUI. Approvals via `--yes` / CLI flags as documented in the agent README.

## Related

- [HLD](02_hld.md)  
- [Specs](06_specs.md) (CompletionPolicy table)  
- [Architecture](01_architecture.md)  
