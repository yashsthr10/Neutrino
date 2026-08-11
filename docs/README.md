# Neutrino system docs

System-level documentation for the Neutrino coding-agent runtime. Deep package APIs stay next to their code (`src/*/README.md`, `src/*/docs/`). This folder answers **how the system fits together**.

## Reading order

1. [Architecture](01_architecture.md) — layers, ownership, import boundaries  
2. [HLD](02_hld.md) — subsystems and responsibilities  
3. [Workflow / codeflow](07_workflow.md) — end-to-end run path  
4. [Specs](06_specs.md) — contracts map  
5. [LLD](03_lld.md) — key modules and types  
6. [Patterns](05_patterns.md) — recurring implementation patterns  
7. [Design](04_design.md) — principles and non-goals  

## Contents

| Doc | Purpose |
|-----|---------|
| [01_architecture.md](01_architecture.md) | Layered stack and dependency rules |
| [02_hld.md](02_hld.md) | High-level design of major subsystems |
| [03_lld.md](03_lld.md) | Low-level modules, entrypoints, core types |
| [04_design.md](04_design.md) | Design principles and trade-offs |
| [05_patterns.md](05_patterns.md) | Ports, fakes, ToolSpec, soft state, events |
| [06_specs.md](06_specs.md) | Spec / contract index |
| [07_workflow.md](07_workflow.md) | Runtime and agent codeflow |

## Package docs (source of truth for APIs)

| Package | User reference | Deep docs |
|---------|----------------|-----------|
| Agent | [`src/agent/README.md`](../src/agent/README.md) | [`src/agent/docs/`](../src/agent/docs/) |
| Orchestrator | [`src/orchestrator/README.md`](../src/orchestrator/README.md) | [`src/orchestrator/docs/`](../src/orchestrator/docs/) |
| Tool Engine | [`src/tool_engine/README.md`](../src/tool_engine/README.md) | [`src/tool_engine/docs/`](../src/tool_engine/docs/) |
| Inference | [`src/inference/README.md`](../src/inference/README.md) | [`src/inference/docs/`](../src/inference/docs/) |
| Credentials | [`src/credentials/README.md`](../src/credentials/README.md) | [`src/credentials/docs/`](../src/credentials/docs/) |
| RNA | [`src/rna/README.md`](../src/rna/README.md) | [`src/rna/docs/`](../src/rna/docs/) |
| Context | [`src/context/README.md`](../src/context/README.md) | [`src/context/docs/`](../src/context/docs/) |
| Protocol | [`protocol/README.md`](../protocol/README.md) | — |
| TUI | [`tui/README.md`](../tui/README.md) | — |
| Living architecture map | [`README.md`](../README.md) | — |

## Quality gates

```bash
make format   # ruff format + safe autofix
make check    # format check, lint, pytest+coverage, TUI checks
make test     # pytest only
```
