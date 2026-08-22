"""Contract tests: Rna and FakeRna both satisfy RnaPort shape."""

from __future__ import annotations

import pytest

from tests.doubles import FakeRna, ScriptedInference
from src.rna import Rna, RnaPort


@pytest.mark.parametrize("impl_name", ["real", "fake"])
def test_port_methods_exist(impl_name: str, rna_python: Rna, fake_rna: FakeRna) -> None:
    impl: RnaPort = rna_python if impl_name == "real" else fake_rna
    assert isinstance(impl, RnaPort)
    for name in (
        "get_symbol",
        "get_file",
        "get_files_with_name",
        "get_import_graph",
        "get_callers",
        "get_tests",
        "get_workflow",
        "get_hld",
        "get_lld",
        "search",
        "semantic_search",
        "google_search",
    ):
        assert callable(getattr(impl, name))


@pytest.mark.parametrize("impl_name", ["real", "fake"])
def test_get_file_shape(impl_name: str, rna_python: Rna, fake_rna: FakeRna) -> None:
    impl = rna_python if impl_name == "real" else fake_rna
    result = impl.get_file("pkg/parser.py")
    assert result.meta is not None
    assert hasattr(result, "data")
    if impl_name == "fake" or result.data is not None:
        assert result.meta.error is None
        assert "parse_request" in (result.data.content if result.data else "")


@pytest.mark.parametrize("impl_name", ["real", "fake"])
def test_get_symbol_shape(impl_name: str, rna_python: Rna, fake_rna: FakeRna) -> None:
    impl = rna_python if impl_name == "real" else fake_rna
    result = impl.get_symbol("parse_request", file_hint="pkg/parser.py")
    assert isinstance(result.data, list)
    if result.data:
        assert result.data[0].name == "parse_request"
        assert result.meta.error is None
    else:
        assert result.meta.error == "not_found"


def test_security_rejects_escape(rna_python: Rna) -> None:
    from src.rna.errors import RnaSecurityError

    with pytest.raises(RnaSecurityError):
        rna_python.get_file("../outside.py")
