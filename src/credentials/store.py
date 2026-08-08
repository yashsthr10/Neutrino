"""Credential persistence backends."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Protocol

from src.credentials.errors import CredentialStoreError
from src.credentials.models import CredentialRecord

logger = logging.getLogger("credentials")

SERVICE_NAME = "neutrino"


def storage_username(profile: str, provider_id: str) -> str:
    return f"{profile}:{provider_id}"


class CredentialStore(Protocol):
    def get(self, profile: str, provider_id: str) -> CredentialRecord | None: ...

    def set(self, profile: str, provider_id: str, record: CredentialRecord) -> None: ...

    def delete(self, profile: str, provider_id: str) -> None: ...

    def list_keys(self, profile: str) -> list[str]: ...


class MemoryStore:
    """In-memory store for tests."""

    def __init__(self) -> None:
        self._data: dict[str, CredentialRecord] = {}

    def get(self, profile: str, provider_id: str) -> CredentialRecord | None:
        return self._data.get(storage_username(profile, provider_id))

    def set(self, profile: str, provider_id: str, record: CredentialRecord) -> None:
        self._data[storage_username(profile, provider_id)] = record

    def delete(self, profile: str, provider_id: str) -> None:
        self._data.pop(storage_username(profile, provider_id), None)

    def list_keys(self, profile: str) -> list[str]:
        prefix = f"{profile}:"
        return sorted(
            k.split(":", 1)[1] for k in self._data if k.startswith(prefix)
        )


class KeyringStore:
    """OS keyring (Secret Service / Keychain / Windows Credential Manager)."""

    def get(self, profile: str, provider_id: str) -> CredentialRecord | None:
        try:
            import keyring
        except ImportError as exc:
            raise CredentialStoreError("keyring is not installed") from exc
        raw = keyring.get_password(SERVICE_NAME, storage_username(profile, provider_id))
        if not raw:
            return None
        try:
            return CredentialRecord.from_storage_dict(json.loads(raw))
        except (json.JSONDecodeError, TypeError, ValueError) as exc:
            raise CredentialStoreError("corrupt keyring credential") from exc

    def set(self, profile: str, provider_id: str, record: CredentialRecord) -> None:
        try:
            import keyring
        except ImportError as exc:
            raise CredentialStoreError("keyring is not installed") from exc
        keyring.set_password(
            SERVICE_NAME,
            storage_username(profile, provider_id),
            json.dumps(record.to_storage_dict()),
        )

    def delete(self, profile: str, provider_id: str) -> None:
        try:
            import keyring
            from keyring.errors import PasswordDeleteError
        except ImportError as exc:
            raise CredentialStoreError("keyring is not installed") from exc
        try:
            keyring.delete_password(SERVICE_NAME, storage_username(profile, provider_id))
        except PasswordDeleteError:
            return

    def list_keys(self, profile: str) -> list[str]:
        # keyring has no portable list API; callers use known provider catalog.
        return []


class EncryptedFileStore:
    """Fernet-encrypted JSON file fallback under ~/.config/neutrino/."""

    def __init__(self, path: Path, *, password: str | None = None) -> None:
        self.path = path
        self._password = password or "neutrino-local-dev-only"
        self._cache: dict[str, CredentialRecord] | None = None

    def _fernet(self):
        import base64
        import hashlib

        from cryptography.fernet import Fernet

        digest = hashlib.sha256(self._password.encode("utf-8")).digest()
        key = base64.urlsafe_b64encode(digest)
        return Fernet(key)

    def _load(self) -> dict[str, CredentialRecord]:
        if self._cache is not None:
            return self._cache
        if not self.path.is_file():
            self._cache = {}
            return self._cache
        try:
            token = self.path.read_bytes()
            raw = self._fernet().decrypt(token)
            data = json.loads(raw.decode("utf-8"))
            out: dict[str, CredentialRecord] = {}
            for k, v in data.items():
                out[k] = CredentialRecord.from_storage_dict(v)
            self._cache = out
            return out
        except Exception as exc:  # noqa: BLE001
            raise CredentialStoreError(f"failed to read encrypted store: {exc}") from exc

    def _save(self, data: dict[str, CredentialRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {k: v.to_storage_dict() for k, v in data.items()}
        token = self._fernet().encrypt(json.dumps(payload).encode("utf-8"))
        self.path.write_bytes(token)
        self._cache = data

    def get(self, profile: str, provider_id: str) -> CredentialRecord | None:
        return self._load().get(storage_username(profile, provider_id))

    def set(self, profile: str, provider_id: str, record: CredentialRecord) -> None:
        data = dict(self._load())
        data[storage_username(profile, provider_id)] = record
        self._save(data)

    def delete(self, profile: str, provider_id: str) -> None:
        data = dict(self._load())
        data.pop(storage_username(profile, provider_id), None)
        self._save(data)

    def list_keys(self, profile: str) -> list[str]:
        prefix = f"{profile}:"
        return sorted(
            k.split(":", 1)[1] for k in self._load() if k.startswith(prefix)
        )


def default_store(*, prefer_keyring: bool = True) -> CredentialStore:
    if prefer_keyring:
        try:
            import keyring  # noqa: F401

            return KeyringStore()
        except Exception:  # noqa: BLE001
            logger.debug("keyring unavailable; using encrypted file store")
    from src.config.paths import user_config_dir

    return EncryptedFileStore(user_config_dir() / "credentials.enc")
