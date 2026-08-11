# Design

Principles and trade-offs that should stay true as Neutrino evolves. Update this when a principle changes — not when a file moves.

## Core bets

1. **Runtime owns safety and completion; the LLM owns depth.**  
   Approvals, budgets, verify-after-write, and DONE/CONTINUE/BLOCKED are deterministic. How many RNA reads or how large a patch is a model choice inside those rails.

2. **One continuous AGENT loop (Claude Code–style).**  
   No hard PLAN → EXECUTE → VERIFY state machine. Soft phases (`DISCOVER` … `DONE`) guide the prompt; workflow status stays `AGENT` until CompletionPolicy finishes the run.

3. **CompletionPolicy is the only DONE authority.**  
   A model “final” is a *candidate*. The orchestrator may CONTINUE with an L6 nudge (same history) or BLOCKED after exhausted repair cycles.

4. **Presentation is a projection.**  
   The TUI (and future clients) must not encode business rules. They speak protocol + render `UIEvent`s.

5. **Tools are intentions over services.**  
   LLM-facing names (`rna.find_symbol`, `executor.apply`) sit in Tool Engine; domain logic stays in RNA / Execution / Verification / Context behind capabilities.

6. **On-demand, bounded knowledge.**  
   RNA answers factual questions with caps and confidence. Context composes ranked packages under token/file/line budgets — it is not a second knowledge API.

7. **Secrets stay out of config files.**  
   Profiles in TOML; credentials from CLI → env → keyring → encrypted store.

8. **Degrade gracefully; fail hard only on invariant violations.**  
   Soft misses use `meta.error` / `meta.degraded`. Path escape and cross-session memory violations raise security errors.

## Soft control surfaces

| Surface | Why it exists |
|---------|----------------|
| Soft `AgentState` (L5) | Tell the model where evidence says we are without locking the FSM |
| L6 reminders | Ephemeral, event-sourced nudges that must not pollute persisted history |
| ToolSpec `when_to_use` / `when_not_to_use` / `pairs_with` | Single source for schemas **and** prompt L2 |

## Non-goals

Neutrino is **not**:

- A general chat product without a repo runtime  
- An eager whole-repo indexer that must finish before the first tool call  
- A UI that decides whether tests are required  
- A place to store API keys in `config.toml`  
- A second copy of RNA inside the agent package  

## Trade-offs we accept

| Choice | Cost | Benefit |
|--------|------|---------|
| Continuous AGENT + CompletionPolicy | More policy code in orchestrator | Model flexibility; fewer brittle phase bugs |
| Capability indirection | Extra layer vs calling services from the loop | Testable boundaries; stable tool names |
| Dual RNA surfaces (library + MCP) | Schema generation discipline | Same facade for in-process and external agents |
| Soft phases in the UI | Can confuse “status” vs “phase” | Better operator visibility without hard FSM |

## Related

- [Architecture](01_architecture.md)  
- [Patterns](05_patterns.md)  
- Root living map: [`README.md`](../README.md)  
