"""Repo analyzer tests."""

from __future__ import annotations

import pytest

from src.rna import Rna
from src.rna.errors import RnaSecurityError
from src.rna.repo_analyzer.files import FileService
from src.rna.repo_analyzer.tree import RepoTree


def test_list_files_ignores_cache(rna_python: Rna) -> None:
    files = rna_python.tree.list_files()
    assert "pkg/parser.py" in files
    assert "tests/test_parser.py" in files
    assert not any(".rna_cache" in f for f in files)
    assert not any(".context_cache" in f for f in files)


def test_get_file_denies_agent_caches(python_repo) -> None:
    from src.rna.config import RnaConfig

    cache_blob = python_repo / ".context_cache" / "packages" / "blobs" / "deadbeef.json"
    cache_blob.parent.mkdir(parents=True, exist_ok=True)
    cache_blob.write_text('{"secret": true}', encoding="utf-8")
    rna_blob = python_repo / ".rna_cache" / "blob.json"
    rna_blob.parent.mkdir(parents=True, exist_ok=True)
    rna_blob.write_text('{"secret": true}', encoding="utf-8")

    rna = Rna(
        RnaConfig(
            repo_path=python_repo,
            cache_dir=python_repo / ".rna_cache",
        )
    )
    files = rna.tree.list_files()
    assert not any(".context_cache" in f for f in files)
    assert not any(f.startswith(".rna_cache/") for f in files)

    with pytest.raises(RnaSecurityError, match="excluded"):
        rna.get_file(".context_cache/packages/blobs/deadbeef.json")
    with pytest.raises(RnaSecurityError, match="excluded"):
        rna.get_file(".rna_cache/blob.json")


def test_get_files_with_name_exact_and_glob(rna_python: Rna) -> None:
    exact = rna_python.get_files_with_name("parser.py")
    assert "pkg/parser.py" in exact.data
    globbed = rna_python.get_files_with_name("**/test_*.py")
    assert any(p.endswith("test_parser.py") for p in globbed.data)


def test_get_file_truncation(python_repo, tmp_path) -> None:
    from src.rna.config import RnaConfig

    big = python_repo / "big.py"
    big.write_text("\n".join(f"line_{i}" for i in range(1, 401)), encoding="utf-8")
    rna = Rna(
        RnaConfig(
            repo_path=python_repo, cache_dir=python_repo / ".rna_cache", max_lines_per_file=200
        )
    )
    result = rna.get_file("big.py")
    assert result.data is not None
    assert result.data.truncated is True
    assert result.data.end_line == 200


def test_path_escape(python_repo) -> None:
    tree = RepoTree(python_repo)
    files = FileService(python_repo, tree)
    try:
        files.resolve_safe("../../etc/passwd")
        raised = False
    except RnaSecurityError:
        raised = True
    assert raised
