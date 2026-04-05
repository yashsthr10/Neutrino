# Neutrino CLI — Repository-Aware Coding, Adaptive Reasoning, and Constraint Graph Planning

## 1. Purpose

This document defines the product vision, principles, and behavior of **Neutrino**: a CLI (TUI) agent that can understand a repository, plan and execute changes safely, verify results, review its output, and adapt how much reasoning it performs based on task complexity.

**Canonical system design** (runtime stack, formal terminology, RNA facade, Neutrino Manager, Intelligence Engine, and numeric limits) is in [`neutrino_full_design.md`](neutrino_full_design.md). **`SPECS.md`** is the technical specification aligned with that design; this README stays at the conceptual level unless noted.

The system is designed around one core idea:

> Use deterministic code for control flow, and use LLMs only where actual reasoning is needed.

That means:
- state machines manage orchestration,
- tools handle file and shell actions,
- agents generate reasoning and code,
- repository structure is modeled as a tree and graph,
- decision-making can branch only when necessary,
- the same tree/graph idea is also used for general reasoning over constraints, dependencies, consequences, and logic paths.

This is not “an LLM that edits files.”  
It is a structured engineering system that uses an LLM as one component inside a larger control architecture.

---

## 2. System Vision

The CLI agent should behave like a disciplined software engineering team, not a free-form chatbot.

It should be able to:
- inspect a repository,
- identify the relevant files and symbols,
- infer constraints and dependencies,
- propose a plan,
- generate a patch,
- run tools,
- verify correctness,
- review output,
- retry or escalate only when needed,
- stop once the job is done.

The system should also be able to reason about non-repo problems, especially system design and architecture problems, by representing:
- constraints as nodes,
- dependencies as edges,
- branches of logic as candidate paths,
- consequences as propagation through a graph,
- alternative approaches as a thought tree,
- outcomes as scored branches.

So the same reasoning machinery works for:
1. repository editing, and
2. abstract planning / system design / consequence analysis.

---

## 3. Core Design Principles

### 3.1 Deterministic Control Flow
All orchestration should be explicit and state-driven.  
The LLM must not decide:
- when the program starts,
- which state comes next,
- when tools are called,
- when to stop,
- when to retry,
- when to apply a patch.

Those decisions belong to the orchestrator.

### 3.2 Adaptive Complexity
Not every task deserves deep reasoning.

The system must classify task complexity and choose the cheapest safe path:
- **Simple** → direct execution with minimal LLM usage.
- **Medium** → plan → execute → verify.
- **Complex** → branch, simulate, score, prune, execute, review.

### 3.3 Context Minimalism
Only relevant context should be sent to the model.  
No full-repo dumping unless absolutely required.

The **Context Builder** enforces hard caps (`MAX_CONTEXT_TOKENS`, `MAX_FILES`, `MAX_LINES_PER_FILE`); see `neutrino_full_design.md` §4.4 and `SPECS.md` §7.4.

Context should be selected using:
- file search,
- tree traversal,
- dependency graph traversal,
- symbol extraction,
- AST slicing,
- recent edit history,
- task-specific relevance scoring.

### 3.4 Diff-Based Editing
The system should prefer patches and line-level changes over whole-file rewrites.

### 3.5 Observability First
Every meaningful decision should be logged:
- state transitions,
- selected mode,
- token usage,
- tool calls,
- prompts,
- outputs,
- retries,
- failures,
- branch scores,
- final decision.

### 3.6 Bounded Reasoning
Branching and retry logic must be strictly limited:
- maximum iterations (including `MAX_REVIEW_ITER` and `MAX_EXEC_ITER`; see `neutrino_full_design.md` §4.5),
- maximum branch count,
- maximum depth,
- token budgets,
- confidence thresholds (enable **early exit** when score or confidence is already sufficient).

### 3.7 Engineering Discipline
The system should behave like an elite engineering team:
- think before acting,
- isolate concerns,
- validate assumptions,
- verify changes,
- review final output,
- prefer clarity over cleverness.

### 3.8 Cost Awareness
The system must be token-aware and latency-aware.

The architecture should minimize:
- unnecessary LLM calls,
- redundant context reprocessing,
- repeated looping,
- broad context expansion,
- expensive branching on trivial tasks.

### 3.9 Single Source of Truth
The `ExecutionContext` must hold the authoritative state of the run. **Neutrino Manager** is the single external interface for orchestration memory; callers do not reach internal **State / Context / Knowledge / Execution History** stores directly (see `neutrino_full_design.md` §4.2).

Agents may propose actions, but the orchestrator owns the actual state transition and effect application.

### 3.10 Chat model backends

Language used by agents (planning, code generation, review, optional classification) is produced through a **single chat-model port**. The project supports three ways to satisfy that port:

- **LangChain** — supply or wrap a LangChain chat model class so you can reuse LangChain prompts, structured output helpers, and observability hooks.
- **Native LLM SDKs** — integrate vendor clients directly (for example OpenAI, Anthropic, Google) behind the same port when you prefer not to route those calls through LangChain.
- **Ollama** — run local models by calling a configurable Ollama server (typical default: `http://127.0.0.1:11434`) for offline use or cheaper iteration.

Only the adapter layer depends on the backend; the FSM, tools, and `ExecutionContext` stay the same regardless of provider.

---

## 4. High-Level Architecture

Conceptual pipeline (user-facing flow):

```text
TUI / CLI Input
   ↓
Input Handler
   ↓
Neutrino Manager (state + memory)
   ↓
Intelligence Engine (routing + strategy: planner / executor / hybrid)
   ↓
RNA Engine (facade: repo, graph, embedding, search, git)
   ↓
Context Builder (capped)
   ↓
Strategy Executor + Agents
   ↓
Chat model port (LangChain / native SDKs / Ollama)
   ↓
Tool Layer + Verification + Review (bounded loops)
   ↓
Apply / Finalize / Fail
```

The **Intelligence Engine** is a **Deterministic Router** plus **Strategy Selector** (rules, thresholds, modes)—not an unconstrained “LLM decides everything” layer. **RNA** is a **facade** over five engines; **Neutrino Manager** is the single orchestration-facing API for session state.

For the full diagram, terminology table, and exact limits, see **`neutrino_full_design.md`**.

Legacy mental model (still valid as a simplification):

```text
CLI
↓
Orchestrator (FSM)
↓
Execution Context + Memory
↓
Repo / Constraint Analysis
↓
Agents + Reasoning Engine
↓
Chat model port (LangChain / native SDKs / Ollama)
↓
Tools / Patch Application / Verification
```

---

## 5. End-to-End Workflow

This is the full workflow of the CLI agent.

### 5.1 User Intent Ingestion
The user enters a task through the CLI, for example:
- “Fix this PR comment”
- “Refactor this function”
- “Add tests for this module”
- “Design a caching strategy for this service”

The CLI parses:
- the task text,
- repository path,
- flags like dry-run, verbose, apply, or deep mode.

### 5.2 Task Classification
The orchestrator classifies the task:
- simple,
- medium,
- complex.

This classification may use:
- heuristics,
- file count,
- diff size,
- dependency count,
- ambiguity,
- risk signals,
- optional LLM fallback if heuristics are uncertain.

### 5.3 Repository Analysis
For code tasks, the system scans:
- directory tree,
- file list,
- relevant symbols,
- imports,
- dependencies,
- tests,
- recent changes.

### 5.4 Context Extraction
The system builds a minimal but useful context bundle containing:
- target files,
- surrounding code slices,
- dependency neighbors,
- relevant tests,
- task constraints,
- current execution metadata.

### 5.5 Planning
If needed, a planner agent breaks the problem into:
- ordered steps,
- constraints,
- likely risks,
- affected files,
- verification targets.

### 5.6 Execution
A coder agent proposes a patch or action.  
The orchestrator applies it through tools:
- read file,
- write patch,
- run command,
- run tests.

### 5.7 Verification
A verifier agent or deterministic verifier checks:
- test results,
- lint results,
- patch validity,
- output consistency,
- unexpected breakages.

### 5.8 Review
A reviewer agent performs final quality control:
- correctness,
- readability,
- maintainability,
- architectural consistency,
- missed edge cases,
- risk assessment.

### 5.9 Finalization
The orchestrator either:
- marks the run as done,
- retries a bounded number of times,
- escalates to a deeper mode,
- or fails gracefully.

---

## 6. Execution Model

The system follows a closed-loop control model:

```text
State -> Agent -> Tool -> Result -> State
```

The orchestrator is the only component that moves the system forward.

The agents are not “free”:
- they do not run arbitrary code,
- they do not touch the filesystem directly,
- they do not decide the global workflow,
- they only produce structured outputs.

---

## 7. State Machine Specification

### 7.1 Primary States

The system should support at least these states:

- `INIT`
- `ANALYZE_REPO`
- `CLASSIFY_TASK`
- `EXTRACT_CONTEXT`
- `PLAN`
- `EXECUTE`
- `VERIFY`
- `REVIEW`
- `BRANCH`
- `DONE`
- `FAIL`

### 7.2 Typical Transition Paths

#### Simple path
```text
INIT -> ANALYZE_REPO -> CLASSIFY_TASK -> EXTRACT_CONTEXT -> EXECUTE -> VERIFY -> REVIEW -> DONE
```

#### Medium path
```text
INIT -> ANALYZE_REPO -> CLASSIFY_TASK -> EXTRACT_CONTEXT -> PLAN -> EXECUTE -> VERIFY -> REVIEW -> DONE
```

#### Complex path
```text
INIT -> ANALYZE_REPO -> CLASSIFY_TASK -> EXTRACT_CONTEXT -> PLAN -> BRANCH -> EXECUTE -> VERIFY -> REVIEW -> DONE
```

### 7.3 Transition Rules
Transitions should be deterministic and guarded by:
- task complexity,
- execution outcome,
- confidence,
- verification status,
- reviewer result,
- retry count,
- token budget,
- timeout or failure conditions.

### 7.4 Orchestrator Responsibility
Only the orchestrator may:
- advance the state,
- trigger the next agent,
- invoke tools,
- apply patches,
- stop the run,
- escalate complexity,
- finalize output.

---

## 8. ExecutionContext Specification

The `ExecutionContext` is the authoritative runtime state.

### 8.1 Required Fields

```python
class ExecutionContext:
    # request
    user_query: str
    repo_path: str

    # classification
    task_complexity: str  # SIMPLE | MEDIUM | COMPLEX
    confidence: float

    # repository understanding
    repo_tree: object
    dependency_graph: object
    symbol_index: object
    relevant_code: dict[str, str]
    recent_changes: list

    # reasoning
    plan_steps: list[str]
    current_step: int
    candidate_branches: list
    selected_branch: object

    # execution
    code_changes: list[dict]
    tool_results: list[dict]
    test_results: dict
    reviewer_feedback: dict

    # cost and control
    token_usage: int
    token_budget: int
    iteration_count: int
    max_iterations: int
    branch_count: int
    max_branches: int
    max_depth: int

    # status
    state: str
    status: str  # RUNNING | DONE | FAIL | ESCALATED

    # observability
    logs: list[dict]
    events: list[dict]
```

### 8.2 Context Rules
- The context is the single source of truth.
- Agents read from context and return structured updates.
- The orchestrator writes to context.
- Context must be bounded and serializable.
- Context should be easy to inspect in logs.

### 8.3 Context Anti-Patterns
Do not:
- store giant raw repo text blobs,
- hide mutable global state elsewhere,
- allow agents to mutate filesystem outside tools,
- let the context grow without pruning,
- mix control flow and reasoning state loosely.

---

## 9. Repository Understanding Layer

The repository understanding layer exists to avoid blind reasoning.

### 9.1 Tree Representation
The tree models:
- directories,
- files,
- nesting,
- locality,
- path relationships.

Example:
```text
repo/
  src/
    parser.py
    utils.py
  tests/
    test_parser.py
```

### 9.2 Graph Representation
The graph models:
- imports,
- symbol dependencies,
- call relationships,
- file interaction,
- test-to-code linkage.

Example:
```text
parser.py -> utils.py
test_parser.py -> parser.py
```

### 9.3 AST / Symbol Extraction
When possible, the system should extract:
- function definitions,
- class definitions,
- methods,
- import statements,
- call sites,
- relevant blocks.

### 9.4 Context Expansion Rules
Context expansion should be controlled:
- start from target file(s),
- expand to dependency neighbors only if needed,
- include relevant tests,
- include surrounding code windows,
- prune irrelevant chunks.

### 9.5 Repo Analysis Caching
Repo analysis should be cached so that repeated tasks do not recompute:
- tree,
- graph,
- symbol index,
- embeddings,
- file metadata.

---

## 10. Context Extraction Engine

The context extraction engine is one of the most important cost-saving parts of the system.

### 10.1 Objective
Extract only the information necessary to solve the task.

### 10.2 Input Signals
- user query,
- task type,
- repo tree,
- graph neighbors,
- symbol index,
- file search results,
- recent edits,
- test relevance,
- risk level.

### 10.3 Output
A compact context package with:
- focused code slices,
- relevant tests,
- constraints,
- dependencies,
- task summary,
- desired output format.

### 10.4 Extraction Strategy
1. Identify candidate files.
2. Locate relevant symbols.
3. Slice surrounding code.
4. Expand to direct dependencies.
5. Deduplicate.
6. Compress.
7. Attach only what the current state requires.

### 10.5 Cost Principle
Do not dump the whole repo into the prompt just because it exists.  
Treat context as a scarce resource.

---

## 11. Task Classification and Adaptive Reasoning

### 11.1 Complexity Classes
The system must classify every task into one of:
- `SIMPLE`
- `MEDIUM`
- `COMPLEX`

### 11.2 Complexity Signals
Possible signals include:
- number of files touched,
- amount of semantic change,
- dependency breadth,
- test impact,
- ambiguity of request,
- architectural consequences,
- likelihood of hidden regressions,
- needed reasoning depth.

### 11.3 Execution Modes

#### SIMPLE
Use when the change is small and localized.
- minimal planning,
- minimal context,
- direct edit and verify.

#### MEDIUM
Use when the task crosses file boundaries or involves moderate logic.
- plan,
- execute,
- verify,
- maybe one retry.

#### COMPLEX
Use when the task affects design, architecture, many dependencies, or unclear semantics.
- branch,
- simulate,
- score,
- prune,
- execute selected branch,
- review.

### 11.4 Escalation
The system should escalate only when needed:
- test failure,
- low confidence,
- reviewer rejection,
- hidden dependency conflicts,
- plan mismatch,
- unexpected tool output.

---

## 12. Reasoning Engine

The reasoning engine is how the system thinks about work before doing it.

### 12.1 Planner Agent
The planner:
- breaks the task into steps,
- identifies risks,
- identifies dependencies,
- identifies likely edit locations,
- suggests verification points,
- estimates effort.

### 12.2 Coder Agent
The coder:
- generates diffs,
- proposes actual code changes,
- obeys constraints,
- respects style and architecture.

### 12.3 Verifier Agent
The verifier:
- inspects tool outputs,
- checks tests,
- identifies failures,
- determines whether execution is safe to continue.

### 12.4 Reviewer Agent
The reviewer:
- performs final quality check,
- catches missed issues,
- checks architectural consistency,
- can reject the patch and force re-execution.

### 12.5 Structured Output Contract
Every agent should return structured output, not raw prose alone.

```python
class AgentOutput:
    action: str
    payload: dict
    reasoning: str
    confidence: float
```

---

## 13. Branching Thought Engine

Branching reasoning is only used when complexity requires it.

### 13.1 Purpose
The branch engine explores multiple possible approaches before committing to one.

### 13.2 Thought Node Model
Each thought node represents a candidate action or plan path.

```python
class ThoughtNode:
    action: str
    context_snapshot: object
    constraints_state: object
    score: float
    risks: list[str]
    children: list["ThoughtNode"]
```

### 13.3 Branching Flow
1. Generate candidate approaches.
2. Simulate consequences.
3. Propagate effects through the constraint/dependency graph.
4. Score each branch.
5. Prune weak branches.
6. Select the best branch.
7. Execute only the selected path.

### 13.4 Branch Limits
Branching must be bounded:
- max branches,
- max depth,
- pruning threshold,
- token budget.

### 13.5 Why It Exists
This is how the system models:
- alternate code solutions,
- alternate architecture paths,
- alternate design decisions,
- alternate consequences of a change.

---

## 14. Constraint Graph Reasoning

The same tree/graph thinking used for repo analysis also applies to general reasoning.

### 14.1 Why It Exists
Humans do not think linearly only.  
We think in:
- constraints,
- relationships,
- consequences,
- branches,
- dependencies,
- tradeoffs.

### 14.2 Constraint Nodes
A constraint node represents a requirement or limitation.

Examples:
- must not break tests,
- must preserve API compatibility,
- must keep latency low,
- must remain readable,
- must avoid overengineering,
- must stay within token budget.

### 14.3 Constraint Edges
Edges represent how constraints influence each other.

Example:
- improving performance may reduce readability,
- adding branching may increase token cost,
- reducing context may increase risk,
- adding validation may improve safety,
- changing an API may affect callers and tests.

### 14.4 Propagation
When a proposed action changes one node, the impact should be propagated through connected nodes to estimate downstream effects.

### 14.5 Use Cases
This is essential for:
- system design reasoning,
- architecture decisions,
- refactor planning,
- tradeoff analysis,
- consequence prediction.

---

## 15. Scoring and Decision Functions

Every branch or candidate plan should be scored.

### 15.1 Typical Factors
- correctness,
- safety,
- readability,
- maintainability,
- performance,
- risk,
- token cost,
- latency cost,
- architectural consistency.

### 15.2 Example Weighted Score
```python
score = (
    correctness * 0.40 +
    safety * 0.20 +
    readability * 0.15 +
    maintainability * 0.10 +
    performance * 0.10 -
    risk * 0.05
)
```

### 15.3 Purpose
The score exists so the system does not choose branches randomly or emotionally.  
It chooses the best path according to explicit engineering criteria.

---

## 16. Tooling Layer

### 16.1 Tool Responsibilities
The tool layer performs deterministic actions only:
- file read,
- patch application,
- search,
- shell execution,
- tests,
- formatting,
- linting,
- repo queries.

### 16.2 Tool Requirements
Tools must be:
- stateless,
- logged,
- bounded,
- explicit,
- safely invoked by the orchestrator.

### 16.3 Required Tools
- `read_file(path)`
- `search_repo(query)`
- `apply_patch(diff)`
- `run_command(cmd)`
- `run_tests()`

### 16.4 Tool Output Handling
Tool results are written back to context and used to decide:
- retry,
- continue,
- escalate,
- fail,
- review.

---

## 17. Verification and Review

### 17.1 Verification
Verification is objective and tool-driven.

Checks may include:
- tests pass,
- file content is valid,
- diff applies cleanly,
- static checks pass,
- formatting is acceptable,
- output aligns with the task.

### 17.2 Review
Review is a quality gate that checks more subjective engineering properties:
- correctness,
- maintainability,
- code smell,
- architectural fit,
- edge cases,
- missing safeguards,
- hidden regressions.

### 17.3 Review Feedback Loop
If the reviewer rejects the result:
- the orchestrator records feedback,
- the system returns to execution,
- the patch is refined,
- verification is repeated.

---

## 18. Cost and Latency Management

Cost is primarily driven by token usage and repeated reasoning loops.  
Latency is driven by tool calls, model calls, and branch exploration.

### 18.1 Token Controls
The system should maintain:
- token budget per task,
- estimated token usage,
- actual token usage,
- budget thresholds,
- downgrade policies.

### 18.2 Latency Controls
The system should reduce latency by:
- using FSM for control flow,
- caching repo analysis,
- limiting branching,
- using minimal context,
- running safe actions in parallel when possible,
- reusing prior extracted context.

### 18.3 Complexity Gating
Use deep reasoning only when needed.  
If a task is simple, do not invoke the expensive path.

### 18.4 Early Exit
If confidence is high and verification passes, the system should stop immediately instead of continuing to “think.”

---

## 19. Observability and Telemetry

A serious system must be observable.

### 19.1 Required Logs
- state transitions,
- selected mode,
- prompt construction metadata,
- token counts,
- branch scores,
- tool calls,
- test results,
- reviewer decisions,
- final status.

### 19.2 Structured Events
Each event should ideally include:
- timestamp,
- state,
- action,
- source agent,
- cost,
- outcome,
- error (if any).

### 19.3 Debugging Value
Good telemetry is what lets you understand:
- why the tool chose a path,
- where it spent tokens,
- why it failed,
- where the context became too large,
- whether branching was justified.

---

## 20. Failure Handling

Failure is normal. The system must fail safely.

### 20.1 Failure Categories
- invalid patch,
- test failure,
- tool failure,
- confidence too low,
- runaway token usage,
- unresolved branch ambiguity,
- reviewer rejection,
- missing context,
- inconsistent state.

### 20.2 Recovery Policy
The system should:
- retry a bounded number of times,
- escalate if needed,
- reduce reasoning depth when possible,
- stop if the budget is exhausted,
- always leave a clear trace.

### 20.3 Safe Failure
A safe failure means:
- no partial uncontrolled edits,
- no hidden state corruption,
- no uncaptured error,
- no infinite loop.

---

## 21. Security and Safety

Even though this is a coding tool, it must not behave like an uncontrolled shell.

### 21.1 Safety Rules
- tools must be explicit,
- shell execution should be controlled,
- patch application must be validated,
- no unrestricted file operations,
- no hidden command execution,
- no unsafe autonomy.

### 21.2 Patch Safety
Before applying a patch:
- validate file path,
- validate diff syntax,
- check target file existence,
- preview the change when possible,
- keep rollback capability in mind.

---

## 22. Package Architecture

The repository implements the **`neutrino`** package under `src/neutrino/`. A layout aligned with `neutrino_full_design.md` may grow as follows (names map to design concepts):

```text
src/neutrino/
  entry.py                 # CLI / app entry
  tui/                     # TUI (Textual): input handling, panels, commands
  orchestrator/            # FSM, transitions, bounded retries
  state/                   # session state; evolves toward Neutrino Manager stores
  config/
  ports/                   # orchestrator and other ports (hexagonal boundaries)
  # Planned / to add as the stack matures:
  # intelligence/          # Deterministic Router + Strategy Selector
  # rna/                     # facade + repo | graph | embedding | search | git
  # context_builder/       # capped context assembly
  # agents/
  # llm/
  # tools/
  # prompts/
  # telemetry/
  # utils/
  tests/
```

### 22.1 Suggested Responsibilities

#### `tui/`
- Textual app, widgets, command palette, streaming and diff views (user **Input Handler** surface).

#### `orchestrator/`
- FSM,
- transitions,
- retry logic bounded by `MAX_EXEC_ITER` / `MAX_REVIEW_ITER` policy,
- execution control.

#### `state/`
- `ExecutionContext` or session state,
- serialization,
- updates,
- pruning (with Context Builder limits from `neutrino_full_design.md` §4.4).

#### `intelligence/` (when added)
- deterministic routing,
- strategy selection (planner / executor / hybrid),
- rules, thresholds, modes.

#### `rna/` (when added)
- **facade** composing **Repo Analyzer**, **Graph Engine**, **Embedding Engine**, **Search Engine**, **Git Analyzer**.

#### `context_builder/` (when added)
- minimal prompt assembly subject to `MAX_CONTEXT_TOKENS`, `MAX_FILES`, `MAX_LINES_PER_FILE`.

#### `agents/` (when added)
- planner,
- coder,
- verifier,
- reviewer.

#### `llm/`
- chat-model port (protocol / base class),
- LangChain chat model adapter,
- native vendor SDK adapters,
- Ollama HTTP adapter,
- factory or registry from configuration.

#### `tools/`
- filesystem tools,
- shell tools,
- test tools,
- search tools.

#### `prompts/`
- prompt builders,
- templates,
- structured prompt composition.

#### `telemetry/`
- logs,
- traces,
- metrics,
- token accounting.

#### `utils/`
- helpers,
- diff utilities,
- safe parsing,
- formatting.

---

## 23. Implementation Strategy

### 23.1 Recommended Build Order
1. Define `ExecutionContext`.
2. Define state machine.
3. Define tool interfaces.
4. Define agent interface and **chat-model port** (with mock + one real backend: e.g. Ollama or a native SDK).
5. Implement CLI.
6. Implement repository tree analysis.
7. Implement context extraction.
8. Implement simple execution path.
9. Add verifier and reviewer.
10. Add adaptive complexity routing.
11. Add thought engine branching.
12. Add constraint graph reasoning.
13. Add telemetry and optimization.

### 23.2 Why This Order
This avoids building clever reasoning before the system can even execute a safe patch.

---

## 24. Non-Goals

The system should not:
- use the LLM for all control flow,
- dump the entire repo into prompt context,
- branch everywhere by default,
- depend on free-form agent communication,
- become a generic chatbot,
- rely on hidden magic instead of structured design.

---

## 25. Success Metrics

The system is successful if it can:
- solve simple edits with very low token usage,
- handle medium tasks with a structured plan,
- handle hard tasks with branch reasoning,
- keep context small,
- stay stable under repeated use,
- produce readable logs,
- avoid unnecessary overengineering,
- recover from failures gracefully.

---

## 26. Final Summary

Neutrino is a controlled reasoning system for software engineering.

It combines:
- deterministic orchestration and **Neutrino Manager**–backed state,
- **Intelligence Engine** routing (deterministic router + strategy selector),
- **RNA**-facaded repository understanding (repo, graph, embedding, search, git),
- constrained **Context Builder** and bounded feedback loops (see `neutrino_full_design.md`),
- constraint graph reasoning,
- branching thought exploration where appropriate,
- adaptive complexity routing,
- strict tool usage,
- verification and review loops,
- token and latency awareness.

The key idea is not to let the model think everywhere.  
The key idea is to let the system decide where thinking is actually worth it.

That is how the tool stays:
- cheaper,
- faster,
- safer,
- more reliable,
- and more engineering-grade than a naive always-think agent.
