"""FSM phase → allowed tool names (state-aware registry filter)."""

from __future__ import annotations

RUNTIME_STATES = frozenset(
    {"INIT", "PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW", "DONE", "CANCELLED"}
)

# Intention-based tool catalogs used by allowlists below.
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
# VERIFY may inspect the tree and run approved shell checks without apply tools.
_VERIFY_INSPECT = frozenset(
    {
        "context.refresh",
        "rna.find_tests",
        "rna.list_files",
        "rna.read_file",
        "executor.run",
    }
)

STATE_ALLOWLIST: dict[str, frozenset[str]] = {
    "INIT": frozenset(),
    "DONE": frozenset(),
    "CANCELLED": frozenset(),
    "PLAN": _CONTEXT_ALL | _RNA_ALL | _RESEARCH_ALL | _PLANNING_ALL,
    "CONTEXT": _CONTEXT_ALL | _RNA_ALL | _RESEARCH_ALL | _PLANNING_ALL,
    # Allow context.resolve in EXECUTE so the model can gather facts before apply.
    "EXECUTE": frozenset({"context.refresh", "context.resolve"})
    | _RNA_ALL
    | _EXECUTOR_ALL
    | _GIT_ALL
    | _PLANNING_ALL
    | frozenset({"tests.run"}),
    "VERIFY": _VERIFY_INSPECT | _VERIFY_ALL | _PLANNING_ALL,
    "REVIEW": _VERIFY_INSPECT | _VERIFY_ALL | _PLANNING_ALL,
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
