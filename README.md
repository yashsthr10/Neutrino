# Neutrino — Architecture (living)

Concise map of what exists. Update this file when a component lands or changes role.

## Idea

Deterministic runtime owns **safety and completion** (approvals, budgets, verify-after-write).  
The LLM owns **how deep to go** inside one continuous Agent loop (Claude Code–style).  
Presentation clients render state and send commands — no business logic in the UI.

## Stack (now)

```
Ink TUI (tui/)  --NDJSON JSON-RPC-->  Python runtime (src/rpc)
                                         └─ AgentOrchestrator (default)
                                         └─ DummyOrchestrator if NEUTRINO_ORCHESTRATOR=dummy
OrchestratorPort + UIEvent             (src/ports)
Agent Loop + L1–L6 prompts             (src/agent)       Inference ↔ Tool Engine cycle
Orchestrator                           (src/orchestrator)
   └─ CompletionPolicy + soft AgentState + env probe
   └─ WorkflowController (status façade: INIT→AGENT→DONE)
Tool Engine                            (src/tool_engine)  LLM ↔ capabilities (open AGENT surface)
   └─ Capability Layer → Context / RNA / Execution / Git / Verification
Inference                              (src/inference)   chat/stream via InferencePort
   └─ Credential Manager               (src/credentials)
RNA                                    (src/rna)
Context                                (src/context)     ChatModelPort ← Inference adapter
Execution                              (src/execution)   apply / shell / git
Verification                           (src/verification) lint / tests runners
Config + profiles                      (src/config)
```

| Layer | Path | Status |
|-------|------|--------|
| Ink TUI | `tui/` | Live — `/auth` keys, `/model` (creds-gated providers) |
| Presentation protocol | `protocol/` | v1.0.0 NDJSON JSON-RPC |
| RPC bridge | `src/rpc/` | Live — AgentOrchestrator default; dummy via env |
| Orchestrator port | `src/ports/orchestrator_port.py` | Contract defined |
| Agent Loop | `src/agent/` | Live — loop, L1–L6 prompts, reminders, soft state |
| Orchestrator | `src/orchestrator/` | Live — continuous AGENT + CompletionPolicy |
| Dummy / fake orch | `src/rpc/dummy.py`, `src/orchestrator/fake.py` | UI smoke stand-in |
| Tool Engine | `src/tool_engine/` | Live — open `AGENT` catalog + when/not-when metadata |
| Inference | `src/inference/` | Live — OpenAI-compatible, LangChain natives, Fake |
| Credentials | `src/credentials/` | Live — keyring/env/encrypted; CLI `neutrino-auth` |
| RNA | `src/rna/` | Implemented (CLI `rna`, MCP optional) |
| Context manager | `src/context/` | Implemented; ChatModel via Inference adapter |
| Execution | `src/execution/` | Live — patch/search_replace/udiff apply, shell, git |
| Verification | `src/verification/` | Live — configurable lint/test runners + waive policy |
| Config | `src/config/` | Inference profiles + legacy `model.*` alias |
| Entry | `src.entry` → `neutrino` | Spawns Ink TUI |

## Runtime path

1. `neutrino` → Node Ink app (`tui/`)
2. TUI spawns `python -m src.rpc` (pipes; stderr for logs)
3. `session.hello` → `runtime.execute` / cancel / approve / …
4. `AgentOrchestrator` runs one continuous **AGENT** loop:
   - Prompt compiler (L1–L6) each model turn
   - Model chooses tools / depth (soft phases: DISCOVER → … → DONE)
   - `CompletionPolicy` decides DONE / CONTINUE / BLOCKED
5. Runtime pushes `ui.event` notifications; TUI reducer → transcript

Set `NEUTRINO_ORCHESTRATOR=dummy` to force the scripted stand-in (tests / UI-only smoke).

### CompletionPolicy (short)

| Situation | Result |
|-----------|--------|
| Final with no successful `executor.apply` | `DONE` (`no_writes`) — Q&A / explore |
| Apply + checks not required | `DONE` (`checks_waived`) |
| Apply + tests/lint green | `DONE` (`checks_green`) |
| Apply + checks still needed | `CONTINUE` + reminder nudge |
| Max repair cycles exceeded | `BLOCKED` (`tests_not_green`) |

Details: [`src/orchestrator/README.md`](src/orchestrator/README.md), [`src/agent/README.md`](src/agent/README.md).

## Agent CLI

```bash
# Real model (uses config + credentials)
python -m src.agent --repo . "add a docstring to src/agent/loop.py"
# or: neutrino-agent "…"

# Auto-approve shell tools
python -m src.agent --yes "run the unit tests"

# Offline smoke (no network)
python -m src.agent --fake "ping"
```

## Tool Engine (`src/tool_engine`)

| Piece | Role |
|-------|------|
| `engine.py` | `schemas_for_state` / `invoke` |
| `capabilities/` | Maps intention tools → Context/RNA/Execution ports |
| `state_policy.py` | `AGENT` allowlist (+ legacy phase aliases) |
| `tools/` | `ToolSpec` catalog with `when_to_use` / `when_not_to_use` |

LLM tools use intention names (`context.resolve`, `rna.find_symbol`, `executor.apply`). Services stay internal.

## TUI (`tui/src`)

| Piece | Role |
|-------|------|
| `app/App.tsx` | Shell, shortcuts |
| `components/Header.tsx` | Status line |
| `components/Stream.tsx` | Chronological transcript |
| `components/CommandBar.tsx` | `>` prompt + slash cmds |
| `components/CommandPalette.tsx` | Ctrl+P |
| `components/InspectorModal.tsx` | Ctrl+R runtime dump |
| `rpc/client.ts` | Child process + NDJSON |
| `state/reducer.ts` | Events → view model |

No sidebar / multi-panel dashboard. Diffs and phase lines render inline in the stream.

## Python RPC (`src/rpc`)

| Module | Role |
|--------|------|
| `framing.py` | Locked NDJSON stdout |
| `mapper.py` | `UIEvent` → `ui.event` |
| `server.py` | JSON-RPC dispatch; wires AgentOrchestrator |
| `dummy.py` | Scripted UI smoke (emits legacy PLAN/EXECUTE/VERIFY markers; not the real AGENT loop) |
| `__main__.py` | `python -m src.rpc` |

## Commands

```bash
pip install -e ".[dev]"
cd tui && npm install && npm run build
neutrino                          # or: cd tui && npm start
python -m src.rpc                 # protocol debug (stdin NDJSON)
python -m src.agent "your task"   # headless agent loop
rna --help                        # RNA CLI
neutrino-auth list                # Credential Manager CLI
pytest tests/agent tests/orchestrator tests/tool_engine tests/execution tests/rpc
```

## Inference + Credentials

| Piece | Role |
|-------|------|
| `src/inference` | `InferenceManager` / `InferencePort`; factory → providers |
| `src/credentials` | Resolve secrets (CLI → env → keyring → encrypted) |
| `src/config` | Non-secret `InferenceProviderConfig` + profiles |
| `InferenceChatModelAdapter` | Bridges Context `ChatModelPort` |

Runtime imports only the Inference Port/Manager — never httpx/LangChain at call sites. No API keys in TOML.

## Task complexity

`fast` → `SIMPLE`, `deep` → `COMPLEX` (retrieval budget for Context Manager).  
Not yet inferred from the query text. Soft phases and CompletionPolicy are independent of this knob.

## Next (not done)

Streaming deltas in the agent loop, Ask/Plan/Debug product modes as allowlist variants, real `auto` complexity classifier, checkpoint/resume across process restarts, parallel tool scheduling.
