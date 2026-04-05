"""Prompt field: submit keys intercepted in _on_key (bindings are unreliable on TextArea)."""

from __future__ import annotations

from textual import events
from textual.widgets import TextArea

from src.tui.messages import SubmitPrompt


def _key_variants(event: events.Key) -> set[str]:
    """All key ids Textual attached to this event (lower-cased)."""
    out: set[str] = set()
    for raw in (event.key, *event.aliases):
        out.add(raw.lower())
    return out


def _is_submit_key(event: events.Key) -> bool:
    """True if this key should send the prompt."""
    for k in _key_variants(event):
        if k in _EXACT_SUBMIT:
            return True
        parts = k.split("+")
        # Any spelling the terminal uses: ctrl+enter, ctrl+shift+enter, etc.
        if "ctrl" in parts and ("enter" in parts or "return" in parts):
            return True
        # Some stacks label keypad Enter differently but still include ctrl + enter token
        if "ctrl" in parts:
            for p in parts:
                if "enter" in p or "return" in p:
                    return True
    return False


_EXACT_SUBMIT: frozenset[str] = frozenset(
    {
        "f2",
        "ctrl+enter",
        "ctrl+return",
    }
)


class PromptTextArea(TextArea):
    """Multiline prompt; Ctrl+Enter / F2 submit via explicit key handling."""

    async def _on_key(self, event: events.Key) -> None:
        if _is_submit_key(event):
            event.stop()
            event.prevent_default()
            self.post_message(SubmitPrompt())
            return
        await super()._on_key(event)
