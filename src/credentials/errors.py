"""Credential subsystem errors."""

from __future__ import annotations


class CredentialError(Exception):
    """Base credential error."""


class CredentialNotFound(CredentialError):
    """No credential for provider/profile."""


class CredentialStoreError(CredentialError):
    """Underlying store failed."""


class CredentialValidationError(CredentialError):
    """Invalid credential record."""
