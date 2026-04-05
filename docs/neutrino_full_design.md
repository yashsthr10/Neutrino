# Neutrino CLI Agent — System Design & Architecture

This document describes the **implemented** Neutrino architecture: components, boundaries, and operational limits as they exist in the design.

---

## 1. Overview

Neutrino is a terminal-based AI engineering system for repository-aware coding, reasoning, and system design. It combines:

- Deterministic orchestration (FSM)
- Centralized state and memory (**Neutrino Manager**)
- A knowledge and analysis facade (**RNA Engine**) over focused engines
- **Intelligence Engine** (deterministic routing and strategy selection)
- Structured agent pipelines and an interactive **TUI**

**Identity:** A stateful adaptive reasoning engine for codebases — not a thin chat wrapper around a model.

---

## 2. Formal terminology

| Term | Definition |
|------|------------|
| **TUI** | Terminal user interface for command input, streaming output, diffs, and status. |
| **Input Handler** | Normalizes and routes user/system input into Neutrino Manager and downstream stages. |
| **RNA Engine** | **Facade** over knowledge and analysis. Composes focused engines and exposes a **stable API** upward. |
| **Repo Analyzer** | Repository structure and content analysis (behind RNA). |
| **Search Engine** | Codebase retrieval (behind RNA). |
| **Embedding Engine** | Embeddings (behind RNA). |
| **Graph Engine** | Dependency / structure graphs (behind RNA). |
| **Git Analyzer** | Git-aware inspection (behind RNA). |
| **Neutrino Manager** | **Single public interface** for session control and memory. Internally composed of modular stores. |
| **State Store** | Session and durable state (inside Neutrino Manager). |
| **Context Store** | Working context and material under management (inside Neutrino Manager). |
| **Knowledge Store** | Persisted knowledge artifacts (inside Neutrino Manager). |
| **Execution History** | Step and outcome history (inside Neutrino Manager). |
| **Intelligence Engine** | **Deterministic Router** + **Strategy Selector** — not an open-ended “LLM decides policy” layer. |
| **Deterministic Router** | Routes using **rules**, **thresholds**, and **modes**. |
| **Strategy Selector** | Chooses **Planner**, **Executor**, or **Hybrid** pipeline. |
| **Context Builder** | Assembles prompts and context subject to **fixed limits** (tokens, files, lines per file). |
| **Strategy Executor** | Factory-style runner for Planner Mode, Executor Mode, Hybrid Mode. |
| **Agent Layer** | Planner Agent, Coder Agent, Verifier Agent, Reviewer Agent. |
| **Tool Layer** | Concrete tools (files, patches, tests, search, etc.). |
| **Feedback Loop** | Planner / executor / reviewer cycles, **bounded** by iteration caps and **early exit** when score or confidence suffices. |

---

## 3. Architecture

Knowledge, control, execution, and validation are separated. The runtime stack:

```
TUI
  ↓
Input Handler
  ↓
Neutrino Manager (central state)
  ↓
Intelligence Engine (routing + strategy selection)
  ↓
RNA Facade
    ├── Repo Analyzer
    ├── Graph Engine
    ├── Embedding Engine
    ├── Search Engine
    └── Git Analyzer
  ↓
Context Builder
  ↓
Strategy Executor (Factory Pattern)
    ├── Planner Mode
    ├── Executor Mode
    └── Hybrid Mode
  ↓
Agent Layer
    ├── Planner Agent
    ├── Coder Agent
    ├── Verifier Agent
    └── Reviewer Agent
  ↓
Tool Layer
  ↓
Feedback Loop (bounded)
  ↓
Apply Changes
  ↓
State Update (Neutrino Manager)
```

**RNA** is a facade: callers use the RNA API; implementation lives in the five engines above. **Intelligence Engine** is the deterministic router plus strategy selector only. **Feedback** is bounded (**§4.5**). **Context** is capped (**§4.4**).

---

## 4. Component specifications

### 4.1 RNA Engine (facade)

The RNA Engine is a **facade** that composes:

- Repo Analyzer  
- Search Engine  
- Embedding Engine  
- Graph Engine  
- Git Analyzer  

It exposes a **stable API** to the rest of the system. Together, these pieces provide a **world model of the codebase** — structure, dependencies, retrieval, embeddings, and git-aware views — without collapsing all logic into one monolithic module.

```
RNA Engine (facade)
  →
Repo Analyzer | Search Engine | Embedding Engine | Graph Engine | Git Analyzer
```

---

### 4.2 Neutrino Manager

Neutrino Manager is the **only external interface** other layers use for orchestration memory and control-plane state. Internally it is split into:

- **State Store**
- **Context Store**
- **Knowledge Store**
- **Execution History**

```
Neutrino Manager
  ├── State Store
  ├── Context Store
  ├── Knowledge Store
  └── Execution History
```

Callers do not address the stores directly; they go through Neutrino Manager.

---

### 4.3 Intelligence Engine

The Intelligence Engine consists of:

- **Deterministic Router** — applies **rules**, **thresholds**, and **modes** (e.g. complexity, context breadth).
- **Strategy Selector** — selects **planner**, **executor**, or **hybrid** pipeline.

It is **not** a free-form reasoning engine that replaces product policy with unconstrained LLM judgment. Routing and strategy choice remain auditable and deterministic at the policy level.

---

### 4.4 Context Builder — limits

Context assembly is **always** constrained:

| Parameter | Value |
|-----------|--------|
| `MAX_CONTEXT_TOKENS` | `8_000` |
| `MAX_FILES` | `5` |
| `MAX_LINES_PER_FILE` | `200` |

Values may be tuned per deployment or model; the **presence** of hard limits is fixed.

---

### 4.5 Feedback loop — iteration bounds

Planner, executor, and reviewer stages run under **hard caps** and **early termination**:

| Parameter | Value |
|-----------|--------|
| `MAX_REVIEW_ITER` | `2` |
| `MAX_EXEC_ITER` | `3` |

**Early exit:** When **confidence** or **reviewer score** already meets the acceptance threshold, later iterations are skipped by default to limit tokens and latency.

---

## 5. Core components (reference)

### 5.1 TUI

Interactive terminal UI: streaming output, diff rendering, command system, collapsible logs, status bar, command palette.

### 5.2 Strategy Executor

Factory-style dispatch to Planner Mode, Executor Mode, or Hybrid Mode as selected by the Intelligence Engine.

### 5.3 Agents

| Agent | Role |
|-------|------|
| Planner | Produces plans |
| Coder | Applies code changes |
| Verifier | Validates results |
| Reviewer | Scores output; gate e.g. accept when score > threshold (e.g. 8) |

### 5.4 Tool Layer

Representative tools: `read_file`, `apply_patch`, `run_tests`, `search_repo` (exact set per product).

### 5.5 Constraint graph reasoning

Constraints as nodes, dependencies as edges; propagation supports impact analysis.

### 5.6 Thought engine (optional branch handling)

Generate branches, simulate, score, prune, select — used where multi-branch reasoning is enabled.

### 5.7 Cost control

Token budget; context limits (**§4.4**); bounded feedback loops (**§4.5**).

### 5.8 Observability

Logs, token usage, state transitions.

### 5.9 Failure handling

Retry, escalate, fail safe.

---

## 6. Execution flow (summary)

User input → Input Handler → Neutrino Manager → Intelligence Engine (router + strategy) → RNA Facade → Context Builder (capped) → Strategy Executor → Agents → Tools → bounded Feedback Loop → Apply → Neutrino Manager state update.

---

## 7. Design rationale (concise)

- **Facade RNA:** Keeps repository knowledge testable, replaceable, and isolated from orchestration.
- **Single Neutrino Manager API:** Avoids scattered state; internal stores stay swappable.
- **Router + selector:** Separates policy (rules, modes) from execution paths (planner / executor / hybrid).
- **Bounded loops and context:** Predictable cost and latency; avoids unbounded prompt growth.

---

## 8. Summary

Neutrino is a **structured, stateful** system: **RNA** as a facade over five engines, **Neutrino Manager** as one interface over four stores, **Intelligence Engine** as deterministic routing and strategy selection, **context** and **feedback** governed by explicit numeric limits, then apply and state update.
