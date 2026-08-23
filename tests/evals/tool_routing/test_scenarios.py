"""Tool routing eval scenarios (prompt/gate regression)."""

from __future__ import annotations

from src.agent.prompts.gates import (
    should_inject_architecture_diagrams,
    should_inject_edit_formats,
    should_inject_terminal_preferences,
)


class _FakeTool:
    def __init__(self, name: str) -> None:
        self.name = name


def test_architecture_gate_complex_query() -> None:
    tools = [_FakeTool("rna.get_hld"), _FakeTool("rna.get_lld")]
    assert should_inject_architecture_diagrams(
        tools,
        query="show repo architecture",
        task_complexity="COMPLEX",
    )


def test_architecture_gate_simple_query_skipped() -> None:
    tools = [_FakeTool("rna.get_hld")]
    assert not should_inject_architecture_diagrams(
        tools,
        query="fix typo in readme",
        task_complexity="SIMPLE",
    )


def test_edit_gate_implement_phase() -> None:
    tools = [_FakeTool("executor.apply")]
    assert should_inject_edit_formats(
        tools,
        query="hello",
        agent_phase="IMPLEMENT",
    )


def test_terminal_gate_shell_query() -> None:
    tools = [_FakeTool("terminal.run")]
    assert should_inject_terminal_preferences(
        tools,
        query="run pytest",
        agent_phase="DISCOVER",
    )
