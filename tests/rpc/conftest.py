"""Shared fixtures for rpc tests."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _use_dummy_orchestrator(monkeypatch: pytest.MonkeyPatch) -> None:
    """RPC smoke tests expect DummyOrchestrator's scripted UI stream."""
    monkeypatch.setenv("NEUTRINO_ORCHESTRATOR", "dummy")
