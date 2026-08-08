"""JSON-RPC presentation protocol for Neutrino clients (Ink TUI, etc.)."""

from __future__ import annotations

PROTOCOL_VERSION = "1.0.0"
PROTOCOL_MAJOR = 1

CAPABILITIES = (
    "execute",
    "cancel",
    "approve",
    "status",
    "undo",
    "retry",
    "refreshContext",
    "requestRepoTree",
    "selectRecovery",
    "setMode",
    "submitEdit",
    "credentials.list",
    "credentials.set",
    "credentials.remove",
    "inference.catalog",
    "inference.listModels",
    "runtime.setModel",
)
