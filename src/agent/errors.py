"""Agent-loop specific errors."""

from __future__ import annotations


class AgentError(Exception):
    """Base agent error."""


class AgentBlocked(AgentError):
    """Loop stopped by policy (repetition, failures, budget)."""


class AgentCancelled(AgentError):
    """Loop cancelled by user or runtime."""


class AgentFailed(AgentError):
    """Unrecoverable agent failure."""
