"""Ensure context subsystem has no forward deps on agents/orchestrator/reasoning."""

from __future__ import annotations

from pathlib import Path


FORBIDDEN = ("src.agents", "src.orchestrator", "src.reasoning", "src.neutrino_manager")


def test_no_forward_dependencies() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "context"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for bad in FORBIDDEN:
            if f"import {bad}" in text or f"from {bad}" in text:
                offenders.append(f"{path}:{bad}")
    assert offenders == []
