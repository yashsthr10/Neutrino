"""JSON-RPC handlers for Credential Manager (never return secret values)."""

from __future__ import annotations

from typing import Any

from src.credentials.env import KIND_FOR_PROVIDER
from src.credentials.errors import CredentialError
from src.credentials.manager import CredentialManager
from src.credentials.models import KNOWN_PROVIDERS, CredentialRecord


def credentials_list(mgr: CredentialManager, params: dict[str, Any]) -> dict[str, Any]:
    profile = str(params.get("profile") or "default")
    statuses = mgr.list_status(profile=profile)
    return {
        "profile": profile,
        "providers": [
            {
                "providerId": s.provider_id,
                "configured": s.configured,
                "source": s.source,
                "kind": s.kind,
            }
            for s in statuses
        ],
    }


def credentials_set(mgr: CredentialManager, params: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(params.get("providerId") or "").strip()
    if provider_id not in KNOWN_PROVIDERS:
        raise ValueError(
            f"Unknown providerId {provider_id!r}; expected one of {', '.join(KNOWN_PROVIDERS)}"
        )
    profile = str(params.get("profile") or "default")
    fields_raw = params.get("fields") or {}
    if not isinstance(fields_raw, dict):
        raise ValueError("fields must be an object")
    fields = {str(k): str(v) for k, v in fields_raw.items() if v is not None and str(v) != ""}
    if not fields and provider_id != "ollama":
        raise ValueError("fields must include at least one secret value")
    kind = str(params.get("kind") or KIND_FOR_PROVIDER.get(provider_id, "api_key"))
    if provider_id == "ollama":
        kind = "none"
    record = CredentialRecord(kind=kind, fields=fields)  # type: ignore[arg-type]
    try:
        mgr.set(provider_id, record, profile=profile)
    except CredentialError as exc:
        raise ValueError(str(exc)) from exc
    return {"ok": True, "providerId": provider_id, "profile": profile}


def credentials_remove(mgr: CredentialManager, params: dict[str, Any]) -> dict[str, Any]:
    provider_id = str(params.get("providerId") or "").strip()
    if provider_id not in KNOWN_PROVIDERS:
        raise ValueError(f"Unknown providerId {provider_id!r}")
    profile = str(params.get("profile") or "default")
    mgr.delete(provider_id, profile=profile)
    return {"ok": True, "providerId": provider_id, "profile": profile}
