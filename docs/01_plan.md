# 01 — Concrete Build Plan (Execution-Focused, Detailed)

## 1. Objective
Build a CLI-based AI coding system that:
- Understands a repository via **tree + dependency graph**
- Plans changes with explicit steps and risks
- Executes **diff-based edits** safely
- Verifies with tests/tools
- Reviews outputs with enforced engineering standards
- **Adapts reasoning depth** (simple → structured → deep/branching) based on task complexity

---

## 2. Guiding Principles
- **Deterministic Orchestration**: FSM drives all flow
- **Structured Context**: no raw dumps; always curated inputs
- **Separation of Concerns**: agents don’t do everything
- **Safety First**: no direct file edits outside orchestrator
- **Observability**: logs/traces for every decision
- **Adaptive Intelligence**: only pay for deep reasoning when needed

---

## 3. Phase-by-Phase Plan

### Phase 0 — Core Contracts (MANDATORY)
**Goal:** Freeze interfaces so everything else is stable.

Deliverables:
- `ExecutionContext` schema (fields + lifecycle)
- `AgentOutput` schema (action, payload, reasoning, confidence)
- `State` enum + transition table
- `Tool` interface + registry
- **Chat model port** — single interface for agent LLM calls (messages in, completion / structured parse out)
- **Pluggable backends** (implement at least one to ship):
  - LangChain: adapter around a LangChain `BaseChatModel` (or project-standard chat model class)
  - Native: thin wrappers for vendor SDKs (OpenAI, Anthropic, Google, etc.) behind the same port
  - Ollama: HTTP client for local models (`base_url` + model name)
- Configuration surface for provider kind + credentials (env / config), no secrets in agent code
- `Orchestrator` skeleton (loop + handler dispatch)

Acceptance:
- Types compile
- Basic orchestrator loop runs with no-op handlers
- Chat port is mockable; one real backend can be selected by config

Risks:
- Overdesigning schemas → keep minimal but sufficient

---

### Phase 1 — Minimal Working CLI (End-to-End)
**Goal:** A runnable pipeline with a single LLM call via the chat-model port (any supported backend).

Deliverables:
- CLI: `neutrino run "<task>" --repo <path>`
- Load repo path
- Configure chat backend: LangChain model, native SDK, or Ollama (per Phase 0 adapters)
- Single “coder” call → produce patch for one file
- Apply patch (naive)
- Print result + logs

Acceptance:
- Works on small repo
- No crashes
- Basic logs printed

---

### Phase 2 — FSM Orchestrator
**Goal:** Replace linear flow with explicit states.

States:
- INIT → ANALYZE_REPO → PLAN → EXECUTE → VERIFY → REVIEW → DONE/FAIL

Deliverables:
- State handlers (pure functions)
- Transition rules (success/failure/next)
- Retry logic with max iterations
- Structured logging per state

Acceptance:
- Each state executes independently
- Transitions visible in logs

---

### Phase 3 — Multi-Agent Split
**Goal:** Decompose responsibilities.

Agents:
- Planner: creates `Plan` (steps, risks, assumptions)
- Coder: generates patches
- Verifier: runs tests/commands, returns results
- Reviewer: critiques, can reject and request re-run

Deliverables:
- BaseAgent interface
- Prompt builders per agent
- Structured outputs

Acceptance:
- Agents read/write only via `ExecutionContext`
- Reviewer can reject → loop back to EXECUTE

---

### Phase 4 — Repo Understanding
**Goal:** Replace naive context with structural awareness.

Deliverables:
- Directory tree builder
- AST parsing (functions/classes where possible)
- Dependency graph (imports first; calls optional)
- Context retrieval:
  - top-k relevant files
  - dependency neighbors
  - recent edits

Acceptance:
- Context size bounded
- Relevant files selected for tasks

---

### Phase 5 — Tool Layer
**Goal:** Deterministic execution layer.

Tools:
- `read_file(path)`
- `apply_patch(diff)`
- `run_command(cmd)`
- `run_tests()`
- `search_repo(query)`

Deliverables:
- Tool registry + invocation
- Command pattern for tool calls
- Result capture into context

Acceptance:
- Tools are stateless and deterministic
- Failures captured and surfaced

---

### Phase 6 — Adaptive Reasoning
**Goal:** Don’t overpay for intelligence.

Deliverables:
- `TaskClassifier` (heuristic + optional LLM fallback)
- Modes:
  - SIMPLE (fast path)
  - MEDIUM (plan → execute → verify)
  - COMPLEX (enable branching)
- Escalation:
  - failure / low confidence → next mode

Acceptance:
- Simple tasks bypass heavy steps
- Logs show chosen mode and reason

---

### Phase 7 — Thought Engine (Branching)
**Goal:** Explore alternatives only when needed.

Deliverables:
- `ThoughtNode` structure
- Branch generator (k candidates)
- Simulation (lightweight, no file writes)
- Scoring (correctness/readability/perf/risk)
- Pruning (beam search: keep top-k)
- Selection → execute best path

Limits:
- max branches: 3
- max depth: 2

Acceptance:
- Branching used only in COMPLEX mode
- Costs bounded

---

### Phase 8 — Review & Feedback Loop
**Goal:** Enforce engineering discipline.

Deliverables:
- Reviewer scoring rubric
- Rejection → re-execute loop
- Confidence thresholds
- Early exit if high confidence + tests pass

Acceptance:
- Bad outputs get rejected and fixed
- Loop bounded by iteration limit

---

### Phase 9 — Optimization
**Goal:** Production viability.

Deliverables:
- Token budget tracking per task
- Context compression (summaries, AST slices)
- Caching (repo analysis, embeddings, prompts)
- Partial execution (only affected modules)
- Parallelism (where safe)

Acceptance:
- Reduced tokens vs naive baseline
- Latency acceptable for medium tasks

---

## 4. Milestones

### MVP
- End-to-end pipeline works
- One agent, one file edit
- Tests run
- Logs visible

### V2
- Multi-agent + FSM
- Repo understanding
- Verifier + Reviewer loop

### V3
- Adaptive routing
- Branching (limited)
- Cost control

---

## 5. Anti-Goals
- No full-repo dumping into prompts
- No LLM for control flow decisions
- No unbounded loops or branches
- No premature micro-optimizations
