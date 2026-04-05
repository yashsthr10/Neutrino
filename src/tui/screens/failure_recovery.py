"""Modal for FailureRecovery options."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static

from src.ports.orchestrator_port import FailureRecovery as FR


class FailureRecoveryScreen(ModalScreen[str | None]):
    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, fr: FR) -> None:
        super().__init__()
        self._fr = fr

    def compose(self) -> ComposeResult:
        with Vertical(id="recovery-dialog"):
            yield Static(self._fr.message, id="recovery-msg")
            for oid, label in self._fr.options:
                yield Button(label, id=f"opt-{oid}", name=oid)
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("opt-"):
            oid = bid[4:]
            self.dismiss(oid)

    def action_dismiss(self) -> None:
        self.dismiss(None)
