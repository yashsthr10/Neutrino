"""System prompt composition stays aligned with FSM allowlists."""

from __future__ import annotations

from src.agent.prompts import build_system_prompt
from src.tool_engine.state_policy import allowed_tools


def _allowlist_section(text: str) -> str:
    marker = "## Tools allowed in this FSM state"
    assert marker in text
    rest = text.split(marker, 1)[1]
    next_heading = rest.find("\n## ")
    return rest if next_heading < 0 else rest[:next_heading]


def test_plan_prompt_lists_allowlist_not_executor() -> None:
    text = build_system_prompt(
        fsm_state="PLAN",
        user_query="add /health endpoint",
        repo_path="/tmp/repo",
    )
    assert "FSM state: `PLAN`" in text
    assert "add /health endpoint" in text
    section = _allowlist_section(text)
    for name in allowed_tools("PLAN"):
        assert f"`{name}`" in section
    assert "`executor.apply`" not in section
    assert "Never invent tools" in text
    assert "runtime owns control flow" in text.lower() or "runtime owns" in text.lower()


def test_execute_prompt_requires_apply_and_includes_formats() -> None:
    text = build_system_prompt(
        fsm_state="EXECUTE",
        user_query="create empty.py",
        repo_path="/repo",
    )
    assert "`executor.apply`" in _allowlist_section(text)
    assert "*** Begin Patch" in text
    assert "*** Add File:" in text
    assert "no_apply" in text
    assert "<<<<<<< SEARCH" in text


def test_verify_prompt_is_task_aware() -> None:
    text = build_system_prompt(
        fsm_state="VERIFY",
        user_query="check tests",
        repo_path="/repo",
        execution_snapshot=(
            "## Execution snapshot (runtime truth)\n"
            "VERIFY policy: checks **not required** (static_assets_only)."
        ),
    )
    section = _allowlist_section(text)
    assert "`tests.run`" in section
    assert "`verify.probe`" in section
    assert "`executor.run`" in section
    assert "Phase goal — VERIFY" in text
    assert "checks are NOT required" in text or "not required" in text
    assert "static_assets_only" in text
