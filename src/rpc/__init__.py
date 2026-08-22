"""JSON-RPC presentation protocol for Neutrino clients (Ink TUI, etc.)."""

from __future__ import annotations

from src.config.constants import (
    PROTOCOL_MAJOR,
    PROTOCOL_VERSION,
    RPC_CAPABILITIES as CAPABILITIES,
)

__all__ = ["PROTOCOL_VERSION", "PROTOCOL_MAJOR", "CAPABILITIES"]
