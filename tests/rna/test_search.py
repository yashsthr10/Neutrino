"""Lexical search tests."""

from __future__ import annotations

from src.rna import Rna


def test_search_finds_symbol(rna_python: Rna) -> None:
    result = rna_python.search("parse_request")
    assert result.data
    assert any("parser.py" in h.file for h in result.data)


def test_search_glob(rna_python: Rna) -> None:
    result = rna_python.search("parse_request", glob="**/parser.py")
    assert result.data
    assert all(h.file.endswith("parser.py") for h in result.data)
