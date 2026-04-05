"""Multiline REPL-style prompt (submit via Ctrl+Enter / F2 from PromptTextArea)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Label

from src.tui.widgets.prompt_text_area import PromptTextArea


class PromptPanel(Vertical):
    DEFAULT_CSS = """
    PromptPanel {
        height: auto;
        max-height: 10;
        min-height: 6;
        border: solid $boost;
        background: $boost;
    }
    PromptPanel Label {
        padding: 0 1;
        text-style: bold;
        color: $text-muted;
    }
    PromptPanel PromptTextArea {
        min-height: 4;
        max-height: 12;
        height: auto;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="prompt-panel")
        self._area = PromptTextArea(
            placeholder=(
                "Message Neutrino…  F2 = send (always). "
                "Ctrl+Enter = send when your terminal reports it. "
                "Ctrl+Shift+C / Ctrl+Shift+V = clipboard."
            ),
            id="prompt-input",
            show_line_numbers=False,
        )

    def compose(self) -> ComposeResult:
        yield Label("Input")
        yield self._area

    @property
    def area(self) -> PromptTextArea:
        return self._area
