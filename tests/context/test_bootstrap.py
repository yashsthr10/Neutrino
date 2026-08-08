"""Bootstrap construction path."""

from __future__ import annotations

from pathlib import Path

from src.context import (
    ContextConfig,
    ContextManagerPort,
    ConversationManagerPort,
    build_context_subsystem,
)
from src.rna import FakeRna


def test_build_context_subsystem(tmp_path: Path, fake_rna: FakeRna) -> None:
    cfg = ContextConfig(cache_dir=tmp_path / ".context_cache")
    cm, conv = build_context_subsystem(fake_rna, "sess-1", cfg)
    assert isinstance(cm, ContextManagerPort)
    assert isinstance(conv, ConversationManagerPort)
