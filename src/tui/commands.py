"""Slash command routing: UI-local vs orchestrator port."""

from __future__ import annotations

import shlex
from dataclasses import dataclass
from enum import Enum, auto
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from src.ports.orchestrator_port import OrchestratorPort


class CommandTarget(Enum):
    UI = auto()
    ORCH = auto()


@dataclass
class ParsedCommand:
    name: str
    args: list[str]
    raw: str


def parse_slash_line(line: str) -> ParsedCommand | None:
    s = line.strip()
    if not s.startswith("/"):
        return None
    parts = shlex.split(s)
    if not parts:
        return None
    name = parts[0][1:].lower()
    return ParsedCommand(name=name, args=parts[1:], raw=s)


class UICommands(Protocol):
    def action_help(self) -> None: ...
    def action_logs_focus(self) -> None: ...
    def action_toggle_file_tree(self) -> None: ...
    def action_reset(self) -> None: ...


def dispatch(
    cmd: ParsedCommand,
    *,
    ui: UICommands,
    orch: OrchestratorPort,
) -> CommandTarget | None:
    """Return None if command name is unknown."""
    match cmd.name:
        case "help" | "?":
            ui.action_help()
            return CommandTarget.UI
        case "logs":
            ui.action_logs_focus()
            return CommandTarget.UI
        case "reset":
            ui.action_reset()
            return CommandTarget.UI
        case "context":
            orch.request_context_refresh()
            return CommandTarget.ORCH
        case "retry":
            orch.request_retry()
            return CommandTarget.ORCH
        case "mode":
            if len(cmd.args) >= 1:
                m = cmd.args[0].lower()
                if m in ("fast", "deep", "auto"):
                    orch.set_runtime_mode(m)  # type: ignore[arg-type]
            return CommandTarget.ORCH
        case "tree" | "files":
            orch.request_repo_tree()
            return CommandTarget.ORCH
        case _:
            return None
