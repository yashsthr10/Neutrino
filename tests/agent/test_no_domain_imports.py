"""Agent package must not import domain services directly."""

from __future__ import annotations

from pathlib import Path

FORBIDDEN_PREFIXES = (
    "src.rna.",
    "src.execution.",
    "src.verification.",
    "src.context.manager",
)


def test_agent_has_no_domain_service_imports() -> None:
    root = Path(__file__).resolve().parents[2] / "src" / "agent"
    offenders: list[str] = []
    for path in root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            for bad in FORBIDDEN_PREFIXES:
                if f"import {bad}" in stripped or f"from {bad}" in stripped:
                    offenders.append(f"{path.name}:{stripped}")
    assert offenders == []
