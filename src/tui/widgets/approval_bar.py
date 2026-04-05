"""Gemini/Codex-style approval row: summary + action buttons + optional diff preview."""

from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Static

from src.ports.orchestrator_port import ApprovalRequest
from src.tui.messages import ApprovalChosen


class ApprovalBar(Vertical):
    """Docked bar: title, primary actions, optional preview snippet."""

    DEFAULT_CSS = """
    ApprovalBar {
        height: auto;
        background: transparent;
        border: none;
        padding: 0 1 0 1;
        align-horizontal: left;
        content-align: left top;
    }
    ApprovalBar #approval-summary {
        padding: 0 0 0 0;
        color: $text;
        text-style: bold;
        align-horizontal: left;
        content-align: left top;
    }
    ApprovalBar #approval-hint {
        padding: 0 0 1 0;
        color: $text-muted;
        text-style: dim;
        align-horizontal: left;
        content-align: left top;
    }
    ApprovalBar #approval-preview {
        padding: 0 0 1 0;
        color: $text-muted;
        max-height: 12;
        border: none;
        align-horizontal: left;
        content-align: left top;
        width: 100%;
    }
    ApprovalBar Vertical#approval-actions {
        height: auto;
        width: auto;
        max-width: 100%;
        layout: vertical;
        align-horizontal: left;
        align: left top;
    }
    ApprovalBar #approval-actions Button {
        height: auto;
        min-height: 1;
        min-width: 0;
        width: auto;
        border: none;
        background: transparent;
        text-align: left;
        content-align: left middle;
        align-horizontal: left;
        padding: 0;
        margin: 0;
        color: $accent;
        text-style: none;
    }
    ApprovalBar #approval-actions Button:hover {
        background: $foreground 8%;
        color: $text;
    }
    ApprovalBar #approval-actions Button:focus {
        background: $foreground 12%;
        color: $text;
    }
    ApprovalBar #approval-actions Button.-success,
    ApprovalBar #approval-actions Button.-primary,
    ApprovalBar #approval-actions Button.-error,
    ApprovalBar #approval-actions Button.-warning,
    ApprovalBar #approval-actions Button.-default {
        border: none;
        background: transparent;
        color: $accent;
    }
    ApprovalBar #btn-approval-reject {
        color: $error;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="approval-bar")
        self._summary = Static("", id="approval-summary", markup=False)
        self._hint = Static("", id="approval-hint", markup=False)
        self._preview = Static("", id="approval-preview", markup=False)

    def compose(self) -> ComposeResult:
        yield self._summary
        yield self._hint
        yield self._preview
        with Vertical(id="approval-actions"):
            yield Button(
                "Accept",
                id="btn-approval-accept",
                variant="success",
            )
            yield Button(
                "Edit",
                id="btn-approval-edit",
                variant="primary",
            )
            yield Button(
                "View",
                id="btn-approval-view",
                variant="default",
            )
            yield Button(
                "Reject",
                id="btn-approval-reject",
                variant="error",
            )

    def update_request(self, req: ApprovalRequest | None) -> None:
        if req is None:
            self.display = False
            self._summary.update("")
            self._hint.update("")
            self._preview.update("")
            return
        self.display = True
        self._summary.update(f"Review change: {req.summary}")
        self._hint.update(
            "Keys: a accept · e edit · v view · r reject · y/n yes/no " f"· id={req.request_id}"
        )
        preview = (req.preview_snippet or "").strip()
        if preview:
            self._preview.update(preview)
            self._preview.display = True
        else:
            self._preview.update("")
            self._preview.display = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        mapping = {
            "btn-approval-accept": "accept",
            "btn-approval-edit": "edit",
            "btn-approval-view": "view",
            "btn-approval-reject": "reject",
        }
        action = mapping.get(bid)
        if action:
            self.post_message(ApprovalChosen(action))
