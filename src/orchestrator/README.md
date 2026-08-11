# Orchestrator — continuous AGENT + CompletionPolicy

Wires the Agent Loop to the TUI/RPC surface. Owns run lifecycle, environment probing, folding context packages into `ExecutionContext`, and **when a run is allowed to finish**.

```text
AgentOrchestrator
├─ env_probe.probe_environment     → L3 snapshot (git + harness)
├─ WorkflowController              → status façade INIT→AGENT→DONE|CANCELLED
├─ CompletionTracker + evaluate_completion
├─ AgentController / AgentLoop     → continuous fsm_state="AGENT"
└─ UIEvent stream                  → TUI / RPC
```

## Run lifecycle

1. Build `ExecutionContext` (`task_complexity` from `fast`→SIMPLE / `deep`→COMPLEX)  
2. Probe environment; seed verification policy on context  
3. `WorkflowController.start()` → `AGENT`  
4. `controller.run(..., fsm_state="AGENT")`  
5. On phase `COMPLETED` (model final):
   - `evaluate_completion(...)`  
   - **DONE** → mark workflow DONE, `RunFinished(ok=True)`  
   - **CONTINUE** → set pending L6 nudge, `continue_phase` (same history)  
   - **BLOCKED** → `RunFinished(ok=False)`  
6. Approvals: `WAITING_USER` for `executor.run` → TUI approve → resume  

There is **no** hard PLAN→EXECUTE→VERIFY march. Soft phases in the prompt (DISCOVER/IMPLEMENT/…) are advisory; UI may display the soft phase as `fsmState` while the hard status is still `AGENT`.

## CompletionPolicy

| Rule | Decision |
|------|----------|
| Not a model final | CONTINUE |
| No successful `executor.apply` | DONE (`no_writes`) |
| Apply + `checks_required=False` | DONE (`checks_waived`) |
| Apply + tests/lint satisfied | DONE (`checks_green`) |
| Apply + checks missing/failed, cycles left | CONTINUE (`need_verification` + nudge) |
| Max verify cycles exhausted | BLOCKED (`tests_not_green`) |

Implementation: [`completion.py`](completion.py).  
Verification waive/require logic comes from [`src/verification/harness.py`](../verification/harness.py) (`build_verification_policy`).

## Environment probe

[`env_probe.py`](env_probe.py) uses `GitService.status/branch` + `detect_harness` and returns an `EnvironmentSnapshot` dict for prompt L3. Refreshed after successful applies.

## Context folding

Successful `context.resolve` / `expand` / `refresh` projects the serialized package into:

- `ExecutionContext.repository`  
- `ExecutionContext.conversation`  

so L4 can show a working set without re-parsing raw tool results every time.

## WorkflowController

Thin status façade only (`workflow.py`):

- `start()` → AGENT  
- `mark_done()` / `cancel()`  
- `record_tool` keeps legacy flags for status/tests  

Completion authority lives in `CompletionPolicy`, not phase transition tables.

## Runtime mode / complexity

| Mode | `task_complexity` |
|------|-------------------|
| `fast` | SIMPLE |
| `deep` | COMPLEX |
| `auto` | UI label only today — same mapping as non-fast → COMPLEX until a classifier lands |

Complexity mainly changes Context Manager retrieval depth, not CompletionPolicy.

## Tests

```bash
pytest tests/orchestrator
```

## Related

- Agent prompts / soft state: [`../agent/README.md`](../agent/README.md)  
- Tool allowlist: [`../tool_engine/README.md`](../tool_engine/README.md)
