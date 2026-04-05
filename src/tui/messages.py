"""Textual messages for the TUI."""

from __future__ import annotations

from textual.message import Message

from src.ports.orchestrator_port import UIEvent


class OrchestratorEventMessage(Message):
    """Posted from backend thread into the Textual app loop."""

    def __init__(self, event: UIEvent) -> None:
        self.event = event
        super().__init__()


class SubmitPrompt(Message):
    """Posted by the prompt TextArea when user confirms send (e.g. Ctrl+Enter)."""

    bubble = True


class ApprovalChosen(Message):
    """User chose an action from the approval bar (button click)."""

    def __init__(self, action: str) -> None:
        self.action = action
        super().__init__()
