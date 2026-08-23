"""Prompt cache helpers (Anthropic cache_control when enabled)."""

from __future__ import annotations

import os

from src.agent.prompts.compiler import DYNAMIC_BOUNDARY


def prompt_cache_enabled() -> bool:
    return os.environ.get("NEUTRINO_PROMPT_CACHE", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def split_system_for_cache(system: str) -> tuple[str, str]:
    """Return (static_prefix, dynamic_suffix) at the dynamic boundary."""
    marker = DYNAMIC_BOUNDARY
    if marker in system:
        static, dynamic = system.split(marker, 1)
        return static.strip(), dynamic.strip()
    return system.strip(), ""
