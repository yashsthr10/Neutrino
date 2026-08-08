# Neutrino — Architecture (living)

Concise map of what exists. Update this file when a component lands or changes role.

## Idea

Deterministic runtime (FSM, tools, RNA, context) owns control flow. LLMs reason only where needed. Presentation clients render state and send commands — no business logic in the UI.

## Stack (now)

```
Ink TUI (tui/)  --NDJSON JSON-RPC-->  Python runtime (src/rpc)
                                         └─ AgentOrchestrator (default)
                                         └─ DummyOrchestrator if NEUTRINO_ORCHESTRATOR=dummy
OrchestratorPort + UIEvent             (src/ports)
Agent Loop                             (src/agent)       Inference ↔ Tool Engine cycle
WorkflowController                     (src/orchestrator) FSM authority (PLAN→EXECUTE→VERIFY→DONE)
Tool Engine                            (src/tool_engine)  LLM ↔ capabilities
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
| Agent Loop | `src/agent/` | Live — loop, policy, classifier, CLI |
| Workflow / orch | `src/orchestrator/` | Live — `AgentOrchestrator` + FSM |
| Dummy / fake orch | `src/rpc/dummy.py`, `src/orchestrator/fake.py` | UI smoke stand-in |
| Tool Engine | `src/tool_engine/` | Live — context/rna/exec/git/verify tools |
| Inference | `src/inference/` | Live — OpenAI-compatible, LangChain natives, Fake |
| Credentials | `src/credentials/` | Live — keyring/env/encrypted; CLI `neutrino-auth` |
| RNA | `src/rna/` | Implemented (CLI `rna`, MCP optional) |
| Context manager | `src/context/` | Implemented; ChatModel via Inference adapter |
| Execution | `src/execution/` | Live — patch/search_replace/udiff apply, shell, git |
| Verification | `src/verification/` | Live — configurable lint/test runners |
| Config | `src/config/` | Inference profiles + legacy `model.*` alias |
| Entry | `src.entry` → `neutrino` | Spawns Ink TUI |

## Runtime path

1. `neutrino` → Node Ink app (`tui/`)
2. TUI spawns `python -m src.rpc` (pipes; stderr for logs)
3. `session.hello` → `runtime.execute` / cancel / approve / …
4. `AgentOrchestrator` runs Agent Loop (PLAN → EXECUTE → VERIFY → DONE)
5. Runtime pushes `ui.event` notifications; TUI reducer → transcript

Set `NEUTRINO_ORCHESTRATOR=dummy` to force the scripted stand-in (tests / UI-only smoke).

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
| `state_policy.py` | FSM allowlists |
| `tools/` | `ToolSpec` catalog |

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
| `dummy.py` | Scripted PLAN→…→REVIEW stream |
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

## Next (not done)

Streaming deltas in the agent loop, REVIEW phase automation, checkpoint/resume across process restarts, parallel tool scheduling.
