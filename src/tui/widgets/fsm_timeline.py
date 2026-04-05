"""Horizontal FSM state rail below the header."""

from __future__ import annotations

from textual.widgets import Static


class FsmTimeline(Static):
    """Renders known states with the active one highlighted."""

    DEFAULT_CSS = """
    FsmTimeline {
        height: auto;
        dock: top;
        padding: 0 1;
        background: $panel;
        color: $text-muted;
    }
    """

    _STATES = ("INIT", "PLAN", "EXECUTE", "VERIFY", "REVIEW", "DONE")

    def __init__(self) -> None:
        super().__init__(id="fsm-timeline")
        self._active: str = "INIT"
        self.update(self._render_text())

    def _render_text(self) -> str:
        parts: list[str] = []
        for i, s in enumerate(self._STATES):
            if s == self._active:
                parts.append(f"[{s}]")
            else:
                parts.append(s)
            if i < len(self._STATES) - 1:
                parts.append(" ──▶ ")
        return "".join(parts)

    def set_active(self, state: str) -> None:
        self._active = state.upper() if state else "INIT"
        self.update(self._render_text())
