"""Credential Manager — secrets for inference and future integrations."""

from src.credentials.errors import (
    CredentialError,
    CredentialNotFound,
    CredentialStoreError,
    CredentialValidationError,
)
from src.credentials.manager import CredentialManager, build_credential_manager
from src.credentials.models import (
    KNOWN_PROVIDERS,
    CredentialRecord,
    ProviderAuthStatus,
    ResolvedCredentials,
)
from src.credentials.store import EncryptedFileStore, KeyringStore, MemoryStore, default_store

__all__ = [
    "CredentialManager",
    "build_credential_manager",
    "CredentialRecord",
    "ResolvedCredentials",
    "ProviderAuthStatus",
    "KNOWN_PROVIDERS",
    "CredentialError",
    "CredentialNotFound",
    "CredentialStoreError",
    "CredentialValidationError",
    "MemoryStore",
    "KeyringStore",
    "EncryptedFileStore",
    "default_store",
]
