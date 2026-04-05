"""Modal for ExplanationAvailable bullets and simple text previews."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static


class TextPreviewScreen(ModalScreen[None]):
    """Multi-line text (e.g. full file view)."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, title: str, body: str) -> None:
        super().__init__()
        self._title = title
        self._body = body

    def compose(self) -> ComposeResult:
        with Vertical(id="text-preview-dialog"):
            yield Static(self._title, id="text-preview-title")
            yield Static(self._body, id="text-preview-body")
            yield Button("Close", variant="primary", id="btn-close")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()


class ExplainScreen(ModalScreen[None]):
    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, bullets: tuple[str, ...]) -> None:
        super().__init__()
        self._bullets = bullets

    def compose(self) -> ComposeResult:
        lines = ["Why this change", ""] + [f"• {b}" for b in self._bullets]
        with Vertical(id="explain-dialog"):
            yield Static("\n".join(lines), id="explain-body")
            yield Button("Close", variant="primary", id="btn-close")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
