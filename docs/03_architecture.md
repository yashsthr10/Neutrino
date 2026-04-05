# 03 — Architecture (Detailed System Design)

## 1. Overview
A CLI-driven system combining:
- FSM orchestration
- Structured context
- Repo analysis (tree + graph)
- Multi-agent reasoning
- Tool execution
- Feedback loops

---

## 2. Layers

CLI
→ Orchestrator (FSM)
→ Context Engine
→ Repo Analyzer
→ Agents
→ Chat model backends (pluggable)
→ Tools
→ Output

Agent steps that need language generation call a **single chat-model port**. That port is implemented by one of:

- **LangChain** — use or wrap a LangChain `BaseChatModel` (or equivalent chat model class) so prompts stay compatible with the LangChain ecosystem.
- **Native vendor SDKs** — call cloud providers directly (for example OpenAI, Anthropic, Google) when you want to avoid LangChain as a dependency for that path.
- **Ollama** — talk to a local Ollama server over its HTTP API for open-weight or self-hosted models.

The orchestrator and tool layer do not depend on which backend is selected; only the agent + LLM adapter layer does.

---

## 3. Execution Flow

1. Parse CLI input
2. Initialize ExecutionContext
3. Analyze repo → build tree + graph
4. Classify task complexity
5. Route to execution mode
6. Plan (if needed)
7. Execute changes
8. Verify (tests/tools)
9. Review (quality gate)
10. Finalize (DONE/FAIL)

---

## 4. Adaptive Routing

SIMPLE → direct execution
MEDIUM → structured pipeline
COMPLEX → enable Thought Engine

---

## 5. Thought Engine (Conditional)

Components:
- ThoughtNode (state snapshot, action, score, risks)
- Generator (k candidates)
- Simulator (apply virtual changes)
- Scorer (multi-factor)
- Pruner (beam search)
- Selector (best node)

Purpose:
- Explore alternatives
- Reduce failed iterations

---

## 6. Repo Representation

Tree:
- directories/files hierarchy

Graph:
- imports (initial)
- optional: function calls, symbols

Used for:
- context retrieval
- impact analysis

---

## 7. Design Patterns

- State → orchestration
- Strategy → agents/modes
- Builder → prompts
- Command → tools
- Observer → logging
- Composite → repo tree

---

## 8. Data Flow

User → Context → Agent → Tool → Context → Next State

---

## 9. Control Flow

Orchestrator:
- selects state handler
- enforces transitions
- applies changes

Agents:
- propose actions

Tools:
- execute actions

---

## 10. Cost Optimization

- FSM handles control flow
- LLM used sparingly
- Context compressed
- Branching gated by complexity
- Token budget enforced

---

## 11. Observability

Log:
- state transitions
- agent outputs
- tool calls
- token usage
- branch scores
- errors

---

## 12. Chat model integration

- **Port**: A narrow interface (message list in, completion / structured parse out) used by planner, coder, reviewer, and optional classifier paths.
- **LangChain path**: Inject or construct a LangChain chat model; the adapter translates between internal messages and LangChain types.
- **Native SDK path**: One adapter per vendor SDK, same port, for minimal dependencies and full control over retries and streaming.
- **Ollama path**: Adapter targets `http://localhost:11434` (or configured base URL) for local inference; suitable for offline or low-cost iteration.

Selection is configuration-driven (CLI flag, env, or config file). Multiple backends may coexist for different agents in advanced setups, but the default is one global chat model per run.

---

## 13. Philosophy

The system acts like a disciplined engineering team:
- understand → plan → execute → verify → review
- adapt thinking depth
- avoid unnecessary complexity
