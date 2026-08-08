"""Tool Engine errors — mapped to ToolResult at the engine boundary."""

from __future__ import annotations


class ToolEngineError(Exception):
    """Base error for the Tool Engine."""


class ToolNotFound(ToolEngineError):
    """Requested tool is not registered."""


class ToolDisabled(ToolEngineError):
    """Tool exists but is disabled."""


class ValidationError(ToolEngineError):
    """Tool arguments failed schema / required-field checks."""


class PermissionDenied(ToolEngineError):
    """Tool is not allowed in the current runtime state."""


class ExecutionError(ToolEngineError):
    """Handler raised or failed during execution."""


class TimeoutError(ToolEngineError):  # noqa: A001 — matches tool contract name
    """Tool execution exceeded its time budget."""


class Cancelled(ToolEngineError):
    """Tool execution was cancelled."""
