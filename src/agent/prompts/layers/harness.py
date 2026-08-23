"""Per-model harness variants (provider-specific prompt nudges)."""

from __future__ import annotations

from typing import Any

_LOCAL_MARKERS = ("ollama", "openai-compatible", "127.0.0.1", "localhost", ":11434")


def render_harness(harness: dict[str, Any] | None) -> str:
    if not harness:
        return ""
    provider = str(harness.get("provider") or "").lower()
    model = str(harness.get("model") or "").lower()
    combined = f"{provider} {model}"
    lines: list[str] = []

    if any(m in combined for m in _LOCAL_MARKERS):
        lines.extend(
            [
                "## Model harness (local inference)",
                "",
                "- Prefer **one tool call per turn** when tool calling is unreliable.",
                "- Use **`executor.apply`** with small `search_replace` hunks; re-read before retry.",
                "- Prefer **`rna.read_file`** over shell `cat`; prefer **`rna.search`** over shell grep.",
            ]
        )
    elif provider in {"anthropic", "openrouter"} or "claude" in model or "gpt" in model:
        lines.extend(
            [
                "## Model harness (frontier tool-caller)",
                "",
                "- You may batch independent read/search tools in parallel.",
                "- After **`executor.apply`**, run **`tests.run`** or **`lint.run`** when harness exists.",
            ]
        )

    if not lines:
        return ""
    return "\n".join(lines) + "\n"
