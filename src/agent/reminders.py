"""L6 — event-sourced dynamic reminders (ephemeral user-side injection)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ReminderFacts:
    """Facts the host collects during a run for reminder triggers."""

    tools_called: list[str] = field(default_factory=list)
    read_before_apply: bool = False
    apply_attempted: bool = False
    apply_succeeded: bool = False
    last_tool_error: str | None = None
    last_failed_tool: str | None = None
    same_tool_streak: int = 0
    validation_error: bool = False
    file_already_exists: bool = False
    absolute_path_error: bool = False
    checks_required: bool | None = None
    tests_attempted: bool = False
    lint_attempted: bool = False
    iteration: int = 0
    max_iterations: int = 0
    tokens_used: int = 0
    token_budget: int = 0
    question_like: bool = False
    task_complexity: str | None = None
    agent_phase: str | None = None
    has_plan_tasks: bool = False
    plan_mode: bool = False


_CATALOG: list[tuple[str, str]] = [
    (
        "read_before_apply",
        "You have not inspected the existing implementation yet. "
        "Prefer repository evidence (`context.resolve` / `rna.read_file`) "
        "over speculative implementation.",
    ),
    (
        "repeat_failure",
        "The previous tool result contained an error. "
        "Do not repeat the same operation without changing your approach.",
    ),
    (
        "verify_after_apply",
        "You modified production code. "
        "Run the relevant tests (or lint when that is the harness) before declaring completion.",
    ),
    (
        "validation_error",
        "The last tool call failed validation or patch matching. "
        "Re-read the target file and craft a tighter edit.",
    ),
    (
        "file_exists",
        "File already exists for an Add File patch. "
        "Switch to `*** Update File` or `search_replace` — do not retry Add File.",
    ),
    (
        "absolute_path",
        "Your last tool call used an absolute path. Tools require repository-relative "
        "paths (e.g. `info.txt`, not `/home/.../info.txt`). You made that call — "
        "convert the path and retry.",
    ),
    (
        "prefer_answer",
        "This task looks like a question / exploration. "
        "Prefer answering from gathered evidence rather than endless search.",
    ),
    (
        "budget",
        "You are approaching the iteration or token budget. "
        "Prioritize finishing the outcome or summarizing the blocker.",
    ),
    (
        "plan_tasks",
        "This is a complex task without a checklist. "
        "Call `plan.set_tasks` with 3–7 concrete steps before implementing.",
    ),
    (
        "plan_mode",
        "Plan mode is active — explore and plan only. "
        "Do not call `executor.apply`, `terminal.run`, or `git.commit`.",
    ),
]


def observe_tool(
    facts: ReminderFacts,
    *,
    name: str,
    success: bool,
    error_text: str = "",
    same_tool_streak: int = 0,
) -> None:
    facts.tools_called.append(name)
    facts.same_tool_streak = same_tool_streak
    err = (error_text or "").lower()
    if name in {"rna.read_file", "context.resolve", "context.expand"} and success:
        facts.read_before_apply = True
    if name == "executor.apply":
        facts.apply_attempted = True
        if success:
            facts.apply_succeeded = True
        if "already exists" in err or "file already exists" in err:
            facts.file_already_exists = True
    if name == "tests.run":
        facts.tests_attempted = True
    if name == "lint.run":
        facts.lint_attempted = True
    if not success:
        facts.last_failed_tool = name
        facts.last_tool_error = error_text or None
        if "validation" in err or "mismatch" in err or "does not match" in err:
            facts.validation_error = True
        if "absolute path" in err:
            facts.absolute_path_error = True


def build_reminders(facts: ReminderFacts) -> tuple[str, ...]:
    """Return deduped reminder texts for this turn."""
    out: list[str] = []
    triggered: set[str] = set()

    def add(key: str) -> None:
        if key in triggered:
            return
        for k, text in _CATALOG:
            if k == key:
                out.append(text)
                triggered.add(key)
                return

    if facts.apply_attempted and not facts.read_before_apply:
        add("read_before_apply")
    if facts.same_tool_streak >= 2 and facts.last_failed_tool:
        add("repeat_failure")
    if (
        facts.apply_succeeded
        and facts.checks_required is True
        and not facts.tests_attempted
        and not facts.lint_attempted
    ):
        add("verify_after_apply")
    if facts.validation_error:
        add("validation_error")
    if facts.file_already_exists:
        add("file_exists")
    if facts.absolute_path_error:
        add("absolute_path")
    if (
        facts.question_like
        and not facts.apply_attempted
        and facts.iteration >= 6
        and len(facts.tools_called) >= 4
    ):
        add("prefer_answer")
    if facts.plan_mode:
        add("plan_mode")
    if (
        (facts.task_complexity or "").upper() == "COMPLEX"
        and not facts.has_plan_tasks
        and facts.agent_phase not in {None, "DISCOVER"}
        and "plan.set_tasks" not in facts.tools_called
        and not facts.apply_attempted
    ):
        add("plan_tasks")
    if facts.max_iterations and facts.iteration >= max(1, facts.max_iterations - 2):
        add("budget")
    if (
        facts.token_budget
        and facts.tokens_used
        and facts.tokens_used >= int(facts.token_budget * 0.85)
    ):
        add("budget")

    return tuple(out)


def looks_question_like(user_query: str) -> bool:
    q = (user_query or "").strip().lower()
    if not q:
        return False
    if "?" in q:
        return True
    starters = (
        "what ",
        "why ",
        "how ",
        "where ",
        "who ",
        "explain ",
        "describe ",
        "tell me ",
        "summarize ",
        "can you tell",
    )
    return any(q.startswith(s) for s in starters)


def reminder_ids_for_tests() -> list[str]:
    return [k for k, _ in _CATALOG]
