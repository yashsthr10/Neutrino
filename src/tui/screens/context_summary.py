"""Modal listing ContextSummary (files, edges, token budget)."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Static

from src.ports.orchestrator_port import ContextSummary as CS


class ContextSummaryScreen(ModalScreen[None]):
    """Read-only view of structured context."""

    BINDINGS = [("escape", "dismiss", "Close")]

    def __init__(self, summary: CS) -> None:
        super().__init__()
        self._summary = summary

    def compose(self) -> ComposeResult:
        lines: list[str] = [
            "Context",
            "",
            f"Tokens: {self._summary.tokens_used:,}"
            + (
                f" / {self._summary.token_budget:,}"
                if self._summary.token_budget is not None
                else ""
            ),
            "",
            "Files:",
        ]
        for f in self._summary.files:
            lines.append(f"  {f.path}  ({f.line_count} lines)")
        lines.append("")
        lines.append("Edges:")
        if not self._summary.edges:
            lines.append("  (none)")
        for e in self._summary.edges:
            lines.append(f"  {e.from_path} -> {e.to_path}")
        body = "\n".join(lines)
        with Vertical(id="context-dialog"):
            yield Static(body, id="context-body")
            yield Button("Close", variant="primary", id="btn-close")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-close":
            self.dismiss()

    def action_dismiss(self) -> None:
        self.dismiss()
