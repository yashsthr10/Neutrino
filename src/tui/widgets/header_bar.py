"""Title row: Neutrino branding + status strip + token usage bar."""

from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import ProgressBar, Static


class HeaderBar(Vertical):
    DEFAULT_CSS = """
    HeaderBar {
        height: auto;
        dock: top;
        background: $panel;
        padding: 0 1;
    }
    HeaderBar #header-top {
        height: auto;
    }
    HeaderBar #brand {
        width: auto;
        text-style: bold;
        color: $accent;
        padding: 0 2 0 0;
    }
    HeaderBar #status-strip {
        width: 1fr;
        color: $text-muted;
    }
    HeaderBar #token-row {
        height: auto;
        padding-top: 0;
    }
    HeaderBar #token-label {
        width: auto;
        color: $text-muted;
        padding-right: 1;
    }
    HeaderBar ProgressBar {
        width: 1fr;
        height: 1;
    }
    """

    def __init__(self) -> None:
        super().__init__(id="header-bar")
        self._brand = Static("Neutrino", id="brand")
        self._status = Static(
            "Mode: — | Tokens: 0 | Repo: — | State: INIT",
            id="status-strip",
        )
        self._token_label = Static("Tokens", id="token-label")
        self._token_bar = ProgressBar(
            total=100_000,
            show_eta=False,
            id="token-bar",
        )

    def compose(self) -> ComposeResult:
        with Horizontal(id="header-top"):
            yield self._brand
            yield self._status
        with Horizontal(id="token-row"):
            yield self._token_label
            yield self._token_bar

    def update_status(
        self,
        *,
        mode_label: str,
        tokens: int,
        repo_path: Path | None,
        fsm_state: str,
    ) -> None:
        repo_s = "loaded"
        repo_detail = ""
        if repo_path is not None:
            try:
                repo_detail = str(repo_path.resolve())
            except OSError:
                repo_detail = "?"
        if repo_detail:
            self._status.update(
                f"Mode: {mode_label} | Tokens: {tokens} | Repo: {repo_s} ({repo_detail}) | State: {fsm_state}"
            )
        else:
            self._status.update(
                f"Mode: {mode_label} | Tokens: {tokens} | Repo: {repo_s} | State: {fsm_state}"
            )

    def update_token_bar(self, used: int, budget: int | None) -> None:
        total = float(budget) if budget is not None and budget > 0 else 100_000.0
        self._token_bar.update(total=total, progress=float(min(used, int(total))))
        b = budget if budget is not None else int(total)
        self._token_label.update(f"Tokens {used:,} / {b:,}")
