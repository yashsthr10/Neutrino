"""Credential Manager — resolve secrets without exposing storage to Inference."""

from __future__ import annotations

from src.credentials.env import env_config_hints, read_env_record
from src.credentials.errors import CredentialNotFound, CredentialValidationError
from src.credentials.models import (
    KNOWN_PROVIDERS,
    CredentialRecord,
    ProviderAuthStatus,
    ResolvedCredentials,
)
from src.credentials.store import CredentialStore, default_store


class CredentialManager:
    def __init__(
        self,
        store: CredentialStore | None = None,
        *,
        cli_overrides: dict[tuple[str, str], CredentialRecord] | None = None,
    ) -> None:
        self._store = store or default_store()
        self._cli = cli_overrides or {}

    def get(self, provider_id: str, *, profile: str = "default") -> CredentialRecord:
        key = (profile, provider_id)
        if key in self._cli:
            return self._cli[key]
        env_rec = read_env_record(provider_id)
        if env_rec is not None:
            return env_rec
        stored = self._store.get(profile, provider_id)
        if stored is not None:
            return stored
        raise CredentialNotFound(f"No credential for {profile}:{provider_id}")

    def set(self, provider_id: str, record: CredentialRecord, *, profile: str = "default") -> None:
        _validate_record(provider_id, record)
        self._store.set(profile, provider_id, record)

    def delete(self, provider_id: str, *, profile: str = "default") -> None:
        self._store.delete(profile, provider_id)

    def list_status(self, *, profile: str = "default") -> list[ProviderAuthStatus]:
        statuses: list[ProviderAuthStatus] = []
        known_from_store = set(self._store.list_keys(profile))
        for provider_id in KNOWN_PROVIDERS:
            source: str | None = None
            kind = None
            configured = False
            if (profile, provider_id) in self._cli:
                configured = True
                source = "cli"
                kind = self._cli[(profile, provider_id)].kind
            else:
                env_rec = read_env_record(provider_id)
                if env_rec is not None:
                    configured = True
                    source = "env"
                    kind = env_rec.kind
                else:
                    stored = self._store.get(profile, provider_id)
                    if stored is not None or provider_id in known_from_store:
                        # list_keys may be empty on keyring — still try get
                        if stored is None:
                            stored = self._store.get(profile, provider_id)
                        if stored is not None:
                            configured = True
                            source = "keyring"
                            kind = stored.kind
            if not configured and provider_id == "ollama":
                configured = True
                source = source or "local"
                kind = kind or "none"
            if not configured and provider_id == "openai-compatible":
                configured = True
                source = source or "none"
                kind = kind or "none"
            statuses.append(
                ProviderAuthStatus(
                    provider_id=provider_id,
                    profile=profile,
                    configured=configured,
                    source=source,
                    kind=kind,
                )
            )
        return statuses

    def resolve(
        self,
        provider_id: str,
        *,
        profile: str = "default",
        config_hints: dict[str, str] | None = None,
    ) -> ResolvedCredentials:
        hints = dict(config_hints or {})
        hints.update(env_config_hints(provider_id))

        # Local openai-compatible / Ollama: no secret required
        if provider_id in {"openai-compatible", "ollama"} and not read_env_record(provider_id):
            try:
                rec = self.get(provider_id, profile=profile)
            except CredentialNotFound:
                return ResolvedCredentials(
                    provider_id=provider_id,
                    profile=profile,
                    kind="none",
                    fields={},
                    source="local" if provider_id == "ollama" else "none",
                    hints=hints,
                )
            if rec.fields.get("base_url"):
                hints["base_url"] = rec.fields["base_url"]
            return ResolvedCredentials(
                provider_id=provider_id,
                profile=profile,
                kind=rec.kind,
                fields=dict(rec.fields),
                source="keyring",
                hints=hints,
            )

        if provider_id == "bedrock" and hints.get("aws_profile"):
            return ResolvedCredentials(
                provider_id=provider_id,
                profile=profile,
                kind="none",
                fields={},
                source="aws_profile",
                hints=hints,
            )

        key = (profile, provider_id)
        if key in self._cli:
            rec = self._cli[key]
            return ResolvedCredentials(
                provider_id=provider_id,
                profile=profile,
                kind=rec.kind,
                fields=dict(rec.fields),
                source="cli",
                hints=hints,
            )

        env_rec = read_env_record(provider_id)
        if env_rec is not None:
            return ResolvedCredentials(
                provider_id=provider_id,
                profile=profile,
                kind=env_rec.kind,
                fields=dict(env_rec.fields),
                source="env",
                hints=hints,
            )

        stored = self._store.get(profile, provider_id)
        if stored is not None:
            source = (
                "encrypted" if type(self._store).__name__ == "EncryptedFileStore" else "keyring"
            )
            return ResolvedCredentials(
                provider_id=provider_id,
                profile=profile,
                kind=stored.kind,
                fields=dict(stored.fields),
                source=source,  # type: ignore[arg-type]
                hints=hints,
            )

        if provider_id == "openai-compatible":
            return ResolvedCredentials(
                provider_id=provider_id,
                profile=profile,
                kind="none",
                fields={},
                source="none",
                hints=hints,
            )

        if provider_id == "ollama":
            return ResolvedCredentials(
                provider_id=provider_id,
                profile=profile,
                kind="none",
                fields={},
                source="local",
                hints=hints,
            )

        raise CredentialNotFound(f"No credential for {profile}:{provider_id}")


def _validate_record(provider_id: str, record: CredentialRecord) -> None:
    if provider_id == "ollama" and record.kind == "none":
        return
    if record.kind == "api_key" and not record.fields.get("api_key"):
        raise CredentialValidationError(f"{provider_id}: api_key required")
    if record.kind == "bearer" and not record.fields.get("token"):
        raise CredentialValidationError(f"{provider_id}: token required")
    if record.kind == "azure" and not (
        record.fields.get("api_key") or record.fields.get("aad_token")
    ):
        raise CredentialValidationError(f"{provider_id}: api_key or aad_token required")
    if record.kind == "aws":
        if not record.fields.get("access_key_id") or not record.fields.get("secret_access_key"):
            raise CredentialValidationError(
                f"{provider_id}: access_key_id and secret_access_key required"
            )


def build_credential_manager(store: CredentialStore | None = None) -> CredentialManager:
    if store is not None:
        return CredentialManager(store=store)
    return CredentialManager(store=default_store())
