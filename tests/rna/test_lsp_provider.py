"""LSP provider tests — skipped when no server on PATH."""

from __future__ import annotations

import shutil

import pytest

from src.rna.adapters.lsp_provider import LspProvider

HAS_PYLSP = shutil.which("pylsp") is not None or shutil.which("pyright-langserver") is not None


@pytest.mark.skipif(not HAS_PYLSP, reason="no Python language server on PATH")
def test_lsp_find_symbol(python_repo) -> None:
    binary = "pylsp" if shutil.which("pylsp") else "pyright-langserver"
    provider = LspProvider("python", python_repo, binary, timeout_ms=10000)
    if not provider.is_available():
        pytest.skip("LSP failed to initialize")
    try:
        found = provider.find_symbol("parse_request", "pkg/parser.py")
        assert isinstance(found, list)
    finally:
        provider.shutdown()
