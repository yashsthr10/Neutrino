# Agent Loop — Claude Code–style harness

LLM-driven decision cycle over Inference + Tool Engine. The loop does **not** own DONE; the orchestrator’s `CompletionPolicy` does.

```text
AgentController
└─ AgentLoop
   ├─ Prompt compiler (L1–L6)     src/agent/prompts/
   ├─ Soft AgentState             src/agent/state_model.py
   ├─ Reminder facts (L6)         src/agent/reminders.py
   ├─ Classifier / repair         classifier.py, tool_call_repair.py
   └─ Policy guards               policy.py (iterations, streaks, tokens, time)
```

## Control flow (what this package owns)

1. Build inference request: compiled system prompt + history + ephemeral reminders  
2. Call `InferencePort.chat` with `schemas_for_state("AGENT")`  
3. Classify response → tool calls / final / invalid / error  
4. Invoke tools via `ToolEngine` (approval gate for `executor.run`)  
5. Update soft `AgentState` + reminder facts from tool outcomes  
6. Return `AgentResult` (`COMPLETED`, `WAITING_USER`, `BLOCKED`, …)

The orchestrator may call `continue_phase` with the **same message history** when CompletionPolicy returns `CONTINUE`.

## Prompt layers (L1–L6)

| Layer | Module | Content |
|-------|--------|---------|
| L1 | `prompts/layers/core.py` | Tiny immutable identity + response contract |
| L2 | `prompts/layers/capabilities.py` | Tools grouped by category; when/not-when from `ToolSpec` |
| — | `__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__` | Cache-friendly split marker |
| L3 | `prompts/layers/environment.py` | cwd, git, harness (host-supplied dict) |
| L4 | `prompts/layers/task_context.py` | User task, working set, verify policy |
| L5 | `prompts/layers/agent_state.py` | Soft phase DISCOVER…DONE |
| L6 | `reminders.py` | `<system-reminder>` injected as a **request-local** user message |

Compiler entry: `compile_system_prompt(PromptInputs) -> CompiledPrompt`  
Compatibility wrapper: `build_system_prompt(...)` in `prompts/system.py`.

Import boundary: `src/agent` must **not** import `src.rna`, `src.execution`, `src.verification`, or `src.context.manager`. Env/harness snapshots are passed in from the orchestrator.

## Soft AgentState

Host-derived guidance (not a hard FSM):

`DISCOVER → PLAN → IMPLEMENT → VERIFY → REPAIR → DONE`

Updated from tool evidence in `derive_agent_state` (`state_model.py`). Shown in L5 every turn. The model chooses the shortest honest path (Q&A may stop after DISCOVER).

## Reminders (L6)

Event-sourced triggers, for example:

- apply without prior read/resolve  
- repeated identical tool failure  
- apply succeeded but checks still required  
- validation / file-already-exists patch errors  
- question-like thrash → prefer answering  
- approaching iteration/token budget  

Reminders are **ephemeral** (not persisted into controller history).

## CLI

```bash
python -m src.agent --repo . "explain this repo"
python -m src.agent --yes "run the unit tests"
python -m src.agent --fake "ping"
python -m src.agent --timing --yes "…"   # also prints timing JSON at end
```

Live runs always log per-turn model latency (`Model done Nms`) and tool `cost_ms`, plus an end-of-run summary (`timing: model …` / `timing: tools …`).

### Offline tool micro-benchmark (no LLM)

```bash
python -m src.agent.bench_tools --repo . --rounds 3
```

## Tests

```bash
pytest tests/agent
```

Key modules: `test_prompts.py`, `test_reminders.py`, `test_loop_fake.py`, `test_timing.py`, `test_no_domain_imports.py`.

## Related

- Orchestrator + CompletionPolicy: [`../orchestrator/README.md`](../orchestrator/README.md)  
- Tool catalog / AGENT allowlist: [`../tool_engine/README.md`](../tool_engine/README.md)
