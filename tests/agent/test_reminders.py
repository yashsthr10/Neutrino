"""L6 reminder trigger table."""

from __future__ import annotations

from src.agent.reminders import ReminderFacts, build_reminders, looks_question_like, observe_tool


def test_read_before_apply_reminder() -> None:
    facts = ReminderFacts()
    observe_tool(facts, name="executor.apply", success=True)
    texts = build_reminders(facts)
    assert any("not inspected" in t for t in texts)


def test_no_read_reminder_when_resolved_first() -> None:
    facts = ReminderFacts()
    observe_tool(facts, name="context.resolve", success=True)
    observe_tool(facts, name="executor.apply", success=True)
    texts = build_reminders(facts)
    assert not any("not inspected" in t for t in texts)


def test_verify_after_apply() -> None:
    facts = ReminderFacts(checks_required=True)
    observe_tool(facts, name="context.resolve", success=True)
    observe_tool(facts, name="executor.apply", success=True)
    texts = build_reminders(facts)
    assert any("modified production code" in t for t in texts)


def test_repeat_failure() -> None:
    facts = ReminderFacts(same_tool_streak=2)
    observe_tool(
        facts, name="rna.read_file", success=False, error_text="missing", same_tool_streak=2
    )
    texts = build_reminders(facts)
    assert any("Do not repeat" in t for t in texts)


def test_file_exists() -> None:
    facts = ReminderFacts()
    observe_tool(
        facts,
        name="executor.apply",
        success=False,
        error_text="File already exists: foo.py",
    )
    # read_before also fires; ensure file_exists present
    texts = build_reminders(facts)
    assert any("already exists" in t.lower() for t in texts)


def test_question_like_prefer_answer() -> None:
    assert looks_question_like("what is this?")
    facts = ReminderFacts(question_like=True, iteration=6)
    for _ in range(4):
        facts.tools_called.append("rna.search")
    texts = build_reminders(facts)
    assert any("question" in t.lower() for t in texts)


def test_budget() -> None:
    facts = ReminderFacts(iteration=9, max_iterations=10)
    texts = build_reminders(facts)
    assert any("budget" in t.lower() for t in texts)
