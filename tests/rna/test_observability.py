"""Observability: one structured log record per call."""

from __future__ import annotations

import logging

from src.rna import Rna


def test_call_emits_log(rna_python: Rna, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="rna"):
        rna_python.get_files_with_name("parser")
    records = [r for r in caplog.records if "rna.call" in r.getMessage()]
    assert records
    msg = records[-1].getMessage()
    assert "get_files_with_name" in msg
    assert "cost_ms" in msg
