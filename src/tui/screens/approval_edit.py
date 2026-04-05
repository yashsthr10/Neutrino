"""Mini editor for approval edit flow."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, TextArea


class ApprovalEditScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "dismiss", "Cancel")]

    def __init__(self, initial: str) -> None:
        super().__init__()
        self._initial = initial

    def compose(self) -> ComposeResult:
        with Vertical(id="approval-edit-dialog"):
            yield TextArea(self._initial, id="approval-edit-text")
            with Vertical(id="approval-edit-actions"):
                yield Button("Apply", variant="primary", id="btn-apply")
                yield Button("Cancel", id="btn-cancel")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#approval-edit-text", TextArea).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-apply":
            text = self.query_one("#approval-edit-text", TextArea).text
            self.dismiss(text)
        elif event.button.id == "btn-cancel":
            self.dismiss(None)

    def action_dismiss(self) -> None:
        self.dismiss(None)
