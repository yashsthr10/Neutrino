"""Context Subsystem error hierarchy. Reserved for invariant violations — not soft misses."""

from __future__ import annotations


class ContextError(Exception):
    """Base Context Subsystem error."""


class ContextSecurityError(ContextError):
    """Cross-session or cross-scope boundary violation."""


class ContextConfigError(ContextError):
    """Invalid ContextConfig detected at startup."""
