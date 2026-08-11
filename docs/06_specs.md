# Specs

Index of contracts and specifications. This file maps **where the normative detail lives**; it does not duplicate full API surfaces.

## Presentation protocol

| Item | Spec |
|------|------|
| Framing / methods / events | [`protocol/README.md`](../protocol/README.md) |
| TypeScript schema | [`protocol/schema.ts`](../protocol/schema.ts) |
| Version | `1.0.0` (major mismatch → JSON-RPC `-32000`) |

## Runtime ports

| Contract | Location |
|----------|----------|
| `OrchestratorPort` + `UIEvent` union | [`src/ports/orchestrator_port.py`](../src/ports/orchestrator_port.py) |
| `InferencePort` | [`src/inference/ports/`](../src/inference/ports/) |
| RNA facade / `RnaPort` | [`src/rna/docs/02_api_spec.md`](../src/rna/docs/02_api_spec.md), [`src/rna/__init__.py`](../src/rna/__init__.py) |
| Context Manager / Conversation | [`src/context/docs/02_api_spec.md`](../src/context/docs/02_api_spec.md) |
| RNA MCP / tool schema generation | [`src/rna/docs/05_tool_contract_and_safety.md`](../src/rna/docs/05_tool_contract_and_safety.md) |

## Agent tool surface (intention tools)

Normative catalog: [`src/tool_engine/README.md`](../src/tool_engine/README.md) + `src/tool_engine/tools/*.py`.

| Category | Examples |
|----------|----------|
| Context | `context.resolve`, `expand`, `refresh` |
| RNA | `rna.find_symbol`, `read_file`, `search`, `semantic_search`, … |
| Research | `research.web`, `research.docs` (docs stub) |
| Execution | `executor.apply`, `rollback`, `diff`, `run` |
| Verification | `verify.probe`, `tests.run`, `lint.run`, `review.run` (stub) |
| Git | `git.commit`, `undo`, `diff` |
| Planning | `plan.set_tasks` |

State gate: open `AGENT` allowlist (`src/tool_engine/state_policy.py`). Behavioral metadata on each `ToolSpec` is part of the contract (schemas + prompt L2).

## CompletionPolicy

| Situation | Decision |
|-----------|----------|
| Not a model final | CONTINUE |
| Final + no successful `executor.apply` | DONE (`no_writes`) |
| Apply + `checks_required=False` | DONE (`checks_waived`) |
| Apply + tests/lint satisfied | DONE (`checks_green`) |
| Apply + checks missing/failed, cycles left | CONTINUE (`need_verification`) |
| Max verify cycles exhausted | BLOCKED (`tests_not_green`) |

Implementation: [`src/orchestrator/completion.py`](../src/orchestrator/completion.py).  
Harness inputs: [`src/verification/harness.py`](../src/verification/harness.py).

## ExecutionContext

Ownership and immutability rules: [`src/context/docs/05_execution_context.md`](../src/context/docs/05_execution_context.md).

## Quality / contributor gates

| Gate | Command |
|------|---------|
| Format | `make format` |
| Format check + lint + pytest (≥65% cov) + TUI | `make check` |
| Tests only | `make test` |

Coverage floor override: `make check COVERAGE_MIN=70`.

## Related

- [Workflow](07_workflow.md) — how these contracts fire in sequence  
- [Architecture](01_architecture.md) — which layer owns which contract  
