"""Shared fixtures for RNA tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.doubles import FakeRna
from src.rna import Rna
from src.rna.config import RnaConfig

FIXTURES = Path(__file__).parent / "fixtures"
PYTHON_SAMPLE = FIXTURES / "python_sample"
JS_SAMPLE = FIXTURES / "js_sample"


@pytest.fixture
def python_repo(tmp_path: Path) -> Path:
    """Copy python sample into an isolated temp dir with its own cache."""
    import shutil

    dest = tmp_path / "python_sample"
    shutil.copytree(PYTHON_SAMPLE, dest)
    return dest


@pytest.fixture
def rna_python(python_repo: Path) -> Rna:
    cfg = RnaConfig(
        repo_path=python_repo,
        cache_dir=python_repo / ".rna_cache",
        enabled_tiers=("structural",),  # deterministic Tier-1-only for base tests
        cache_enabled=True,
    )
    return Rna(cfg)


@pytest.fixture
def fake_rna() -> FakeRna:
    from src.rna.models import (
        CallEdge,
        ImportEdge,
        SymbolRef,
        TestLink,
    )

    fake = FakeRna()
    fake.files["pkg/parser.py"] = "def parse_request(raw):\n    return raw.split()\n"
    fake.file_names = ["pkg/parser.py", "pkg/router.py", "tests/test_parser.py"]
    fake.symbols["parse_request"] = [
        SymbolRef(
            name="parse_request",
            kind="function",
            file="pkg/parser.py",
            line_start=1,
            line_end=2,
            language="python",
        )
    ]
    fake.import_edges = [
        ImportEdge(from_file="pkg/router.py", to="pkg/parser.py", external=False),
        ImportEdge(from_file="tests/test_parser.py", to="pkg.parser", external=False),
    ]
    fake.callers["parse_request"] = [
        CallEdge(
            caller=SymbolRef(
                name="handle",
                kind="function",
                file="pkg/router.py",
                line_start=4,
                line_end=5,
            ),
            callee_name="parse_request",
            call_site_line=5,
        )
    ]
    fake.tests["pkg/parser.py"] = [
        TestLink(
            test_symbol=None,
            test_file="tests/test_parser.py",
            target="pkg/parser.py",
            relation="direct_import",
            confidence=0.9,
        )
    ]
    return fake
