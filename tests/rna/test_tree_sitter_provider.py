"""Tier-1 tree-sitter golden tests."""

from __future__ import annotations

from src.rna.adapters.tree_sitter_provider import TreeSitterProvider


def test_python_symbols(python_repo) -> None:
    provider = TreeSitterProvider("python", python_repo)
    assert provider.is_available()
    syms = provider.symbols_in_file("pkg/parser.py")
    names = {s.name for s in syms}
    assert "parse_request" in names
    assert "unused_helper" in names


def test_python_imports(python_repo) -> None:
    provider = TreeSitterProvider("python", python_repo)
    edges = provider.find_imports("pkg/router.py")
    assert any("parser" in e.to for e in edges)


def test_python_callers_heuristic(python_repo) -> None:
    provider = TreeSitterProvider("python", python_repo)
    callers = provider.find_callers("parse_request", None)
    assert callers
    assert any(c.caller.file.endswith("router.py") for c in callers)


def test_find_symbol_with_hint(python_repo) -> None:
    provider = TreeSitterProvider("python", python_repo)
    found = provider.find_symbol("parse_request", "pkg/parser.py")
    assert len(found) >= 1
    assert found[0].file == "pkg/parser.py"
