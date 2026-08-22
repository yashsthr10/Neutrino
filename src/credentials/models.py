"""Credential wire models — never log secret field values."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.config.constants import KNOWN_PROVIDERS

CredentialKind = Literal["api_key", "bearer", "azure", "aws", "none"]

__all__ = [
    "KNOWN_PROVIDERS",
    "CredentialKind",
    "CredentialRecord",
    "ResolvedCredentials",
    "ProviderAuthStatus",
]


@dataclass(frozen=True, slots=True)
class CredentialRecord:
    kind: CredentialKind
    fields: dict[str, str] = field(default_factory=dict)

    def to_storage_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "fields": dict(self.fields)}

    @classmethod
    def from_storage_dict(cls, data: dict[str, Any]) -> CredentialRecord:
        kind = str(data.get("kind") or "api_key")
        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            fields = {}
        return cls(kind=kind, fields={str(k): str(v) for k, v in fields.items()})  # type: ignore[arg-type]


@dataclass(frozen=True, slots=True)
class ResolvedCredentials:
    provider_id: str
    profile: str
    kind: CredentialKind
    fields: dict[str, str]
    source: Literal["cli", "env", "keyring", "encrypted", "aws_profile", "none"]
    hints: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ProviderAuthStatus:
    provider_id: str
    profile: str
    configured: bool
    source: str | None = None
    kind: CredentialKind | None = None
