"""Harness detection and task-aware VERIFY policy."""

from __future__ import annotations

from pathlib import Path

from src.verification.harness import build_verification_policy, detect_harness, probe_repo


def test_detect_harness_pytest_markers(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    info = detect_harness(tmp_path)
    assert info.has_tests is True
    assert info.suggested_test_command == "pytest"


def test_detect_harness_empty_repo(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<h1>hi</h1>", encoding="utf-8")
    info = detect_harness(tmp_path)
    assert info.has_tests is False
    assert info.has_lint is False


def test_policy_waives_static_assets_even_with_pytest(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    policy = build_verification_policy(
        tmp_path,
        code_changes=({"path": "index.html", "action": "add"}, {"path": "style.css"}),
        user_query="make a landing page",
    )
    assert policy.checks_required is False
    assert policy.reason == "static_assets_only"


def test_policy_requires_tests_for_python_changes(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    policy = build_verification_policy(
        tmp_path,
        code_changes=({"path": "pkg/mod.py", "action": "update"},),
        user_query="fix hello",
    )
    assert policy.checks_required is True
    assert policy.reason == "test_harness_present"


def test_policy_waives_when_no_harness(tmp_path: Path) -> None:
    (tmp_path / "main.go").write_text("package main\n", encoding="utf-8")
    # go.mod would create a harness — omit it
    policy = build_verification_policy(
        tmp_path,
        code_changes=({"path": "main.go"},),
        user_query="edit main",
    )
    assert policy.checks_required is False
    assert policy.reason == "no_test_or_lint_harness"


def test_probe_repo_returns_sample_paths(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    data = probe_repo(tmp_path, max_paths=10)
    assert data["harness"]["has_tests"] is False
    assert "a.txt" in data["sample_paths"]
