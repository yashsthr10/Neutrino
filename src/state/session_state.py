"""Session-facing state (display + future ExecutionContext bridge)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from src.config.schema import NeutrinoSettings


@dataclass
class SessionState:
    """Mutable view for the TUI; orchestrator will own authoritative truth later."""

    settings: NeutrinoSettings
    last_fsm_state: str = "INIT"
    pending_approval_id: str | None = None

    @property
    def repo_path(self) -> Path:
        return self.settings.repo_path
