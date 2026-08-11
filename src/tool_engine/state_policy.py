"""FSM / agent state → allowed tool names (state-aware registry filter)."""

from __future__ import annotations

RUNTIME_STATES = frozenset(
    {
        "INIT",
        "AGENT",
        "PLAN",
        "CONTEXT",
        "EXECUTE",
        "VERIFY",
        "REVIEW",
        "DONE",
        "CANCELLED",
    }
)

_CONTEXT_ALL = frozenset({"context.resolve", "context.expand", "context.refresh"})
_RNA_ALL = frozenset(
    {
        "rna.find_symbol",
        "rna.trace_workflow",
        "rna.find_tests",
        "rna.find_related",
        "rna.semantic_search",
        "rna.read_file",
        "rna.search",
        "rna.list_files",
    }
)
_RESEARCH_ALL = frozenset({"research.web", "research.docs"})
_EXECUTOR_ALL = frozenset(
    {"executor.apply", "executor.rollback", "executor.diff", "executor.run"}
)
_GIT_ALL = frozenset({"git.commit", "git.undo", "git.diff"})
_VERIFY_ALL = frozenset({"verify.probe", "tests.run", "lint.run", "review.run"})
_PLANNING_ALL = frozenset({"plan.set_tasks"})

# Claude Code–style open surface for the continuous agent loop.
AGENT_TOOLS = (
    _CONTEXT_ALL
    | _RNA_ALL
    | _RESEARCH_ALL
    | _EXECUTOR_ALL
    | _GIT_ALL
    | _VERIFY_ALL
    | _PLANNING_ALL
)

# Legacy phase labels alias to AGENT during migration.
STATE_ALLOWLIST: dict[str, frozenset[str]] = {
    "INIT": frozenset(),
    "DONE": frozenset(),
    "CANCELLED": frozenset(),
    "AGENT": AGENT_TOOLS,
    "PLAN": AGENT_TOOLS,
    "CONTEXT": AGENT_TOOLS,
    "EXECUTE": AGENT_TOOLS,
    "VERIFY": AGENT_TOOLS,
    "REVIEW": AGENT_TOOLS,
}


def normalize_state(state: str | None) -> str:
    if not state:
        return "INIT"
    return state.strip().upper()


def allowed_tools(state: str | None) -> frozenset[str]:
    key = normalize_state(state)
    return STATE_ALLOWLIST.get(key, frozenset())


def is_allowed(tool_name: str, state: str | None) -> bool:
    return tool_name in allowed_tools(state)
