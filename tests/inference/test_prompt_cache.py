"""Prompt cache split helpers."""

from __future__ import annotations

from src.agent.prompts.compiler import DYNAMIC_BOUNDARY
from src.inference.prompt_cache import split_system_for_cache


def test_split_system_at_dynamic_boundary() -> None:
    system = f"static prefix\n{DYNAMIC_BOUNDARY}\ndynamic tail"
    static, dynamic = split_system_for_cache(system)
    assert static == "static prefix"
    assert dynamic == "dynamic tail"


def test_split_system_without_boundary() -> None:
    static, dynamic = split_system_for_cache("all static")
    assert static == "all static"
    assert dynamic == ""
