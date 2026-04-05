# 02 — System Specifications (Strict, Contract-First)

## 1. Core Rule
LLM is used ONLY for:
- Planning
- Reasoning
- Code generation

Everything else MUST be deterministic.

---

## 2. ExecutionContext (Strict Schema)

Required fields:
- user_query: str
- repo_path: str
- repo_tree: object
- dependency_graph: object
- task_complexity: enum {SIMPLE, MEDIUM, COMPLEX}
- plan_steps: list
- current_step: int
- code_changes: list (diffs/patches)
- tool_results: list
- test_results: object
- reviewer_feedback: object
- token_usage: {used: int, budget: int}
- iteration_count: int
- status: enum {INIT, RUNNING, DONE, FAIL}

Constraints:
- Must be the **single source of truth**
- Agents cannot mutate filesystem; only propose changes

---

## 3. Agent Contract

Interface:
- input: ExecutionContext
- output: AgentOutput

AgentOutput:
- action: str  (e.g., "propose_patch", "call_tool")
- payload: dict
- reasoning: str
- confidence: float (0.0–1.0)

Rules:
- No side effects
- No direct file I/O
- Must be deterministic given same input (as far as possible)

---

## 4. Tool Contract

Tools must be:
- Stateless
- Deterministic
- Explicitly invoked

Required tools:
- read_file(path)
- apply_patch(diff)
- run_command(cmd)
- run_tests()
- search_repo(query)

All tool calls:
- logged
- results appended to context

---

## 5. State Machine

States:
- INIT
- ANALYZE_REPO
- PLAN
- EXECUTE
- VERIFY
- REVIEW
- DONE
- FAIL

Rules:
- Orchestrator is the **only authority** for transitions
- Each state has a single handler
- Handlers return next state

---

## 6. Complexity Modes

SIMPLE:
- direct execution
- minimal context
- no planning/branching

MEDIUM:
- plan → execute → verify

COMPLEX:
- plan → branch → simulate → score → execute → review

---

## 7. Limits (Hard Constraints)
- max_iterations: 5
- max_branches: 3
- max_depth: 2
- token_budget must be enforced
- early exit allowed on high confidence

---

## 8. Invariants
- No direct file edits by agents
- All changes via orchestrator + tools
- No unstructured outputs
- No infinite loops
- Context must be bounded
- Logs must exist for every state

---

## 9. Output Contract

Each run must produce:
- Plan summary
- Execution trace (states, actions)
- Tool call history
- Applied diffs
- Test results
- Reviewer decision
- Final status

---

## 10. LLM / Chat Model Contract

**Goal:** Agents invoke language models only through a **chat-model port** so orchestration, tools, and context stay independent of vendor details.

**Supported backend families (all optional at build time; at least one required for a full run):**

| Family | Role |
|--------|------|
| **LangChain chat model** | Use or wrap a LangChain `BaseChatModel`-style class so prompts and chains can reuse LangChain utilities. |
| **Native LLM SDKs** | Direct use of provider SDKs (REST or official clients) behind the same port when LangChain is not desired for that deployment. |
| **Ollama** | Local models via the Ollama HTTP API (default local base URL configurable). |

**Port rules:**

- Input: structured messages (system / user / assistant slices) or an internal equivalent; output: text and/or parsed structured fields as required by `AgentOutput`.
- The port exposes sync and/or async invocation; implementations may stream internally but must surface a complete result to the orchestrator unless streaming is explicitly a first-class feature later.
- Token usage and model id must be observable for telemetry when the backend provides them (Ollama and most SDKs expose usage or approximations).
- Switching backend must not change FSM transitions or tool contracts—only configuration and adapter wiring.

**Configuration (conceptual):**

- Provider kind: `langchain` | `native` | `ollama` (plus vendor-specific ids where needed).
- Credentials and base URLs via environment or secrets, never hard-coded in agent logic.

---

## 11. Acceptance Criteria
- Completes small task end-to-end
- At least one chat-model backend (LangChain, native SDK, or Ollama) can be selected via configuration and used for agent calls
- Avoids overengineering simple tasks
- Recovers from at least one failure
- Logs are inspectable and meaningful
