# Neutrino CLI — Technical Specification

## 1. Overview

**Canonical architecture** (component names, diagrams, and numeric limits) lives in [`neutrino_full_design.md`](neutrino_full_design.md). This document specifies behavior, data shapes, and orchestration; where terms differ, interpret **ExecutionContext** and orchestrator state as the concrete realization of **Neutrino Manager**’s responsibilities and the **Context Builder** output.

This system is a CLI-based autonomous coding agent designed to perform repository-aware code modifications using a hybrid architecture of:

- Deterministic state machine orchestration
- Structured execution context
- Repository structural analysis (tree + dependency graph)
- Multi-agent reasoning
- Tool-based execution
- Adaptive reasoning complexity (simple → structured → deep)

The system prioritizes:

- Cost efficiency (token minimization)
- Deterministic control flow
- High reliability in multi-file code changes

---

## 2. System Goals

### 2.1 Functional Goals

- Modify code based on natural language tasks
- Understand repository structure and dependencies
- Execute changes safely using diff-based edits
- Verify correctness using tools (tests, linting)
- Review output using structured critique

### 2.2 Non-Functional Goals

- Minimize token usage
- Maintain deterministic orchestration
- Ensure observability at every stage
- Avoid unnecessary reasoning complexity
- Support incremental and partial execution

---

## 3. Core Architecture

### 3.1 Canonical runtime stack

Aligned with `neutrino_full_design.md`:

```text
TUI
  → Input Handler
  → Neutrino Manager (central state; single external interface)
  → Intelligence Engine (Deterministic Router + Strategy Selector)
  → RNA Engine (facade)
        Repo Analyzer | Graph Engine | Embedding Engine | Search Engine | Git Analyzer
  → Context Builder (hard limits; see §7.4)
  → Strategy Executor (Planner Mode | Executor Mode | Hybrid Mode)
  → Agent Layer (Planner | Coder | Verifier | Reviewer)
  → Chat model backends (pluggable port; see §3.2)
  → Tool Layer
  → Feedback Loop (bounded; see §15.3)
  → Apply Changes
  → Neutrino Manager (state update)
```

- **RNA Engine** is a **facade**: callers use its stable API; the five engines behind it stay swappable and testable in isolation.
- **Intelligence Engine** is **not** open-ended LLM policy: it applies **rules**, **thresholds**, and **modes**, and selects **planner / executor / hybrid** pipelines only.
- **Neutrino Manager** is the single orchestration-facing interface; internally it decomposes into **State Store**, **Context Store**, **Knowledge Store**, and **Execution History** (logical modules; may map to packages or submodules in code).

### 3.2 LLM / chat model backends

All agent-side language generation (planning, coding, review, optional classification) goes through a **single chat-model abstraction**. The implementation is swappable and may be one of:

| Backend | Description |
|---------|-------------|
| **LangChain chat model** | Use or wrap LangChain’s chat model class (`BaseChatModel` or equivalent) for ecosystem compatibility (chains, callbacks, LangSmith, etc.). |
| **Native LLM vendor SDKs** | Call cloud providers directly via official SDKs or HTTP when you want minimal middleware and full control. |
| **Ollama** | Local inference via the Ollama HTTP API for self-hosted or open-weight models; base URL and model name are configuration. |

Orchestration, state machine, and tools do not branch on backend choice. Configuration (provider, model name, API keys, Ollama URL) is external to agent logic.

---

## 4. Execution Context (Core Data Model)

### 4.1 Definition

`ExecutionContext` is the single source of truth for all system state for a run. Conceptually it is owned and updated through the **Neutrino Manager** boundary: serialized snapshots and working fields correspond to **Context Store** / **State Store** material described in `neutrino_full_design.md` §4.2.

### 4.2 Schema

```python
class ExecutionContext:
    user_query: str
    repo_path: str

    # Repository understanding
    repo_tree: dict
    dependency_graph: dict
    symbol_index: dict

    # Task understanding
    task_complexity: str  # SIMPLE | MEDIUM | COMPLEX
    plan_steps: list[str]
    current_step: int

    # Code interaction
    relevant_code: dict[str, str]
    code_changes: list[dict]

    # Execution feedback
    tool_results: list[dict]
    test_results: dict
    reviewer_feedback: dict

    # Control
    iteration_count: int
    max_iterations: int

    # Cost tracking
    token_usage: int
    token_budget: int

    # Status
    state: str
    status: str  # RUNNING | DONE | FAIL
```

---

## 5. State Machine (Orchestration)

### 5.1 States

- `INIT`
- `ANALYZE_REPO`
- `CLASSIFY_TASK`
- `EXTRACT_CONTEXT`
- `PLAN`
- `EXECUTE`
- `VERIFY`
- `REVIEW`
- `DONE`
- `FAIL`

### 5.2 Transition Rules

| Current State   | Condition              | Next State      |
|-----------------|------------------------|-----------------|
| `INIT`          | always                 | `ANALYZE_REPO`  |
| `ANALYZE_REPO`  | success                | `CLASSIFY_TASK` |
| `CLASSIFY_TASK` | SIMPLE                 | `EXECUTE`       |
| `CLASSIFY_TASK` | MEDIUM/COMPLEX         | `PLAN`          |
| `PLAN`          | done                   | `EXECUTE`       |
| `EXECUTE`       | success                | `VERIFY`        |
| `EXECUTE`       | failure                | RETRY / ESCALATE |
| `VERIFY`        | pass                   | `REVIEW`        |
| `VERIFY`        | fail                   | `EXECUTE`       |
| `REVIEW`        | approved               | `DONE`          |
| `REVIEW`        | rejected               | `EXECUTE`       |
| ANY             | max_iterations exceeded| `FAIL`          |

### 5.3 Invariants

- Only orchestrator mutates state
- State transitions must be explicit
- No implicit loops allowed
- Execution must terminate

---

## 6. Repository Analysis

### 6.1 Tree Construction

- Traverse directory structure
- Store file hierarchy
- Ignore irrelevant directories (e.g., `.git`, `node_modules`)

### 6.2 Dependency Graph

**Initial:**

- File-level import graph

**Optional:**

- Function-level call graph

```python
graph = {
    "file_a.py": ["file_b.py"],
}
```

### 6.3 Symbol Index

**Extract:**

- Functions
- Classes
- Methods

**Used for:**

- Context slicing
- Targeted edits

---

## 7. Context Extraction Engine

### 7.1 Objective

Minimize token usage while preserving relevant information.

### 7.2 Algorithm

1. Identify target files
   - From user query
   - Via search
2. Extract code slices
   - Function-level or block-level
   - Include ±N lines (configurable)
3. Expand via dependency graph
   - Include only direct dependencies
4. Deduplicate and compress

### 7.3 Output

```python
context.relevant_code = {
    "file.py": "sliced code"
}
```

### 7.4 Context Builder — mandatory limits

Context assembly MUST respect these caps (see `neutrino_full_design.md` §4.4). Implementations may expose them as configuration, but unbounded growth is invalid.

| Parameter | Value |
|-----------|--------|
| `MAX_CONTEXT_TOKENS` | `8_000` |
| `MAX_FILES` | `5` |
| `MAX_LINES_PER_FILE` | `200` |

---

## 8. Task Classification

### 8.1 Modes

- `SIMPLE`
- `MEDIUM`
- `COMPLEX`

### 8.2 Heuristics

**SIMPLE:**

- Single file
- Small change

**MEDIUM:**

- Multiple files
- Moderate logic

**COMPLEX:**

- Architecture changes
- Unclear scope
- High dependency impact

### 8.3 Output

```python
context.task_complexity = "SIMPLE"
```

---

## 9. Agent System

Agents call the shared **chat-model port** (LangChain, native SDK, or Ollama backend) for language generation; they do not embed provider-specific APIs.

### 9.1 Agent Interface

```python
class AgentOutput:
    action: str
    payload: dict
    reasoning: str
    confidence: float
```

### 9.2 Agents

| Agent           | Role                              |
|-----------------|-----------------------------------|
| Planner Agent   | Generates steps; identifies risks |
| Coder Agent     | Produces diff-based edits         |
| Verifier Agent  | Validates correctness             |
| Reviewer Agent  | Evaluates quality and completeness |

---

## 10. Execution Engine

### 10.1 Loop

```python
while not done:
    output = agent.run(context)

    if output.action == "edit_code":
        apply_patch()

    elif output.action == "call_tool":
        run_tool()

    update_context()
```

### 10.2 Retry Logic

- Max retries per step
- Escalate complexity if needed

---

## 11. Tool Layer

### 11.1 Tools

- `read_file`
- `apply_patch`
- `run_tests`
- `run_command`
- `search_repo`

### 11.2 Requirements

- Deterministic
- Stateless
- Logged

---

## 12. Branching Thought Engine (Optional)

### 12.1 Activation

Only in `COMPLEX` mode.

### 12.2 Structure

```python
class ThoughtNode:
    state_snapshot
    action
    score
    risks
    children
```

### 12.3 Flow

1. Generate candidates
2. Simulate impact
3. Score
4. Prune (beam search)
5. Select best

---

## 13. Verification

### 13.1 Methods

- Test execution
- Linting
- Static checks

### 13.2 Output

```json
{
    "passed": true,
    "errors": []
}
```

---

## 14. Review System

### 14.1 Criteria

- Correctness
- Readability
- Maintainability
- Edge cases

### 14.2 Behavior

- Approve or reject
- Rejection triggers re-execution

---

## 15. Cost Management

### 15.1 Token Budget

```python
context.token_budget = N
```

### 15.2 Controls

- Context compression
- Limited branching
- Adaptive reasoning
- Caching

### 15.3 Feedback loop — iteration bounds

Planner, executor, and reviewer cycles MUST enforce:

| Parameter | Value |
|-----------|--------|
| `MAX_REVIEW_ITER` | `2` |
| `MAX_EXEC_ITER` | `3` |

**Early exit:** When confidence or reviewer score already meets the acceptance threshold, skip further iterations by default (see `neutrino_full_design.md` §4.5).

---

## 16. Observability

### 16.1 Logs

- State transitions
- Agent outputs
- Tool calls
- Token usage
- Errors

### 16.2 Format

```python
log = {
    "state": "...",
    "action": "...",
    "tokens": 123
}
```

---

## 17. Failure Handling

### 17.1 Cases

- Test failures
- Invalid patch
- Tool errors
- Low confidence

### 17.2 Strategy

- Retry
- Escalate
- Fail gracefully

---

## 18. Security & Safety

- No arbitrary command execution without control
- Sandbox tool execution
- Validate patches before applying

---

## 19. Output

Final output includes:

- Applied changes
- Execution trace
- Verification results
- Review outcome

---

## 20. Summary

The system is a hybrid deterministic + AI-driven pipeline where:

- Control flow is handled by code (FSM / orchestrator), not by the LLM
- **Intelligence Engine** routing and **Strategy Executor** modes choose how much reasoning runs
- **RNA** (facade over repo, graph, embedding, search, git engines) supplies repository understanding
- **Neutrino Manager** centralizes state; **Context Builder** stays within fixed limits; **feedback loops** stay within iteration caps
- Chat models are injected selectively via the pluggable port
- Correctness is enforced through verify/review

This ensures scalability, reliability, and efficiency in real-world codebases.

For the authoritative component diagram and terminology table, see **`neutrino_full_design.md`**.

---

## Implementation Note

This document is an implementation-grade blueprint: it specifies behavior and structure beyond a high-level plan alone. The Neutrino codebase implements the `neutrino` package (`src/neutrino/`); extend modules to match the architecture above.

**Possible next step:** Ask to convert this specification into a code skeleton (Python modules, runnable project layout, orchestrator and agent stubs) to move from reading the spec to building the system.
