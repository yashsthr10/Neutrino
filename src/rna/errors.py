"""RNA error hierarchy. Reserved for invariant violations — not 'not found' cases."""

from __future__ import annotations


class RnaError(Exception):
    """Base RNA error."""


class RnaSecurityError(RnaError):
    """Path traversal, symlink escape, or scope violation."""


class RnaConfigError(RnaError):
    """Invalid configuration detected at startup."""
