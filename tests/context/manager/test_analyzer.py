"""RequirementAnalyzer golden table."""

from __future__ import annotations

import pytest

from src.context.manager.analyzer import RequirementAnalyzer
from src.context.models import ContextRequest


@pytest.fixture
def analyzer() -> RequirementAnalyzer:
    return RequirementAnalyzer()


def _methods(plan) -> list[str]:
    return [m for m, _ in plan.calls]


def test_planner_simple(analyzer: RequirementAnalyzer) -> None:
    plan = analyzer.analyze(
        ContextRequest(
            task_description="fix typo",
            task_complexity="SIMPLE",
            requesting_agent="planner",
            file_hints=("pkg/parser.py",),
        )
    )
    methods = _methods(plan)
    assert "get_file" in methods
    assert "get_files_with_name" in methods
    assert "get_hld" not in methods
    assert plan.query_conversation is True


def test_planner_medium(analyzer: RequirementAnalyzer) -> None:
    plan = analyzer.analyze(
        ContextRequest(
            task_description="add cache",
            task_complexity="MEDIUM",
            requesting_agent="planner",
            file_hints=("pkg/parser.py",),
            symbol_hints=("parse_request",),
        )
    )
    methods = set(_methods(plan))
    assert {"get_file", "get_symbol", "get_callers", "get_import_graph", "get_tests"} <= methods
    assert "get_hld" not in methods


def test_planner_complex(analyzer: RequirementAnalyzer) -> None:
    plan = analyzer.analyze(
        ContextRequest(
            task_description="redesign",
            task_complexity="COMPLEX",
            requesting_agent="planner",
            file_hints=("pkg/parser.py",),
            symbol_hints=("parse_request",),
        )
    )
    methods = set(_methods(plan))
    assert "get_hld" in methods
    assert "get_workflow" in methods


def test_verifier(analyzer: RequirementAnalyzer) -> None:
    plan = analyzer.analyze(
        ContextRequest(
            task_description="verify",
            task_complexity="MEDIUM",
            requesting_agent="verifier",
            file_hints=("pkg/parser.py",),
        )
    )
    methods = set(_methods(plan))
    assert methods == {"get_tests", "get_file"}


def test_capabilities_bypass(analyzer: RequirementAnalyzer) -> None:
    plan = analyzer.analyze(
        ContextRequest(
            task_description="x",
            task_complexity="SIMPLE",
            requesting_agent="planner",
            capabilities=("search", "semantic_search"),
        )
    )
    assert _methods(plan) == ["search", "semantic_search"]
