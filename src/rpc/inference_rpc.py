"""JSON-RPC helpers for inference provider/model selection (creds-gated)."""

from __future__ import annotations

from typing import Any

from src.config.constants import (
    ALWAYS_ELIGIBLE_PROVIDERS as ALWAYS_ELIGIBLE,
    CATALOG_MODEL_LABELS,
    CATALOG_MODELS,
    LOCAL_INFERENCE_HOST_MARKERS,
    OLLAMA_DEFAULT_BASE_URL,
    OLLAMA_DEFAULT_HOST,
    OLLAMA_DEFAULT_TIMEOUT_S,
    OPENROUTER_DEFAULT_BASE_URL,
)
from src.config.schema import InferenceProviderConfig
from src.credentials.manager import CredentialManager
from src.credentials.models import KNOWN_PROVIDERS


def _provider_meta(provider_id: str) -> dict[str, str]:
    if provider_id in {"openai-compatible", "ollama"}:
        return {"type": "openai-compatible", "vendor": ""}
    return {"type": "native", "vendor": provider_id}


def display_provider_id(cfg: InferenceProviderConfig) -> str:
    """Map persisted openai-compatible Ollama URLs back to the ollama provider id."""
    if (
        cfg.type == "openai-compatible"
        and cfg.base_url
        and _looks_like_local_openai_compatible(cfg.base_url)
    ):
        return "ollama"
    return cfg.provider_id()


def _normalize_openai_compatible_base(url: str) -> str:
    base = url.strip().rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def _ollama_base_url(
    credentials: CredentialManager,
    *,
    profile: str = "default",
    explicit: str | None = None,
    active: InferenceProviderConfig | None = None,
) -> str:
    if explicit:
        return _normalize_openai_compatible_base(explicit)
    try:
        resolved = credentials.resolve("ollama", profile=profile)
        stored = resolved.fields.get("base_url") or resolved.hints.get("base_url")
        if stored:
            return _normalize_openai_compatible_base(stored)
    except Exception:  # noqa: BLE001
        pass
    if active and active.base_url and _looks_like_local_openai_compatible(active.base_url):
        return _normalize_openai_compatible_base(active.base_url)
    return _normalize_openai_compatible_base(OLLAMA_DEFAULT_HOST)


def eligible_providers(
    credentials: CredentialManager, *, profile: str = "default"
) -> list[dict[str, Any]]:
    """Providers the user may select models for — only those with credentials.

    ``openai-compatible`` is always included (local Ollama / vLLM often need no key).
    Bedrock with ``aws_profile`` in active config is treated as configured via resolve.
    """
    statuses = {s.provider_id: s for s in credentials.list_status(profile=profile)}
    out: list[dict[str, Any]] = []
    for provider_id in KNOWN_PROVIDERS:
        st = statuses.get(provider_id)
        configured = bool(st and st.configured)
        source = st.source if st else None
        if provider_id in ALWAYS_ELIGIBLE:
            if not configured:
                # Still eligible; resolve may return kind=none
                configured = True
                source = source or "none"
        if not configured:
            continue
        meta = _provider_meta(provider_id)
        out.append(
            {
                "providerId": provider_id,
                "configured": True,
                "source": source,
                "kind": st.kind if st else None,
                "type": meta["type"],
                "vendor": meta["vendor"] or None,
            }
        )
    return out


def catalog(
    credentials: CredentialManager,
    active: InferenceProviderConfig,
    *,
    profile: str = "default",
) -> dict[str, Any]:
    providers = eligible_providers(credentials, profile=profile)
    return {
        "profile": profile,
        "active": {
            "providerId": display_provider_id(active),
            "model": active.model,
            "type": active.type,
            "vendor": active.vendor,
            "baseUrl": active.base_url,
        },
        "providers": providers,
    }


def config_for_provider(
    provider_id: str,
    *,
    model: str | None = None,
    base_url: str | None = None,
    active: InferenceProviderConfig | None = None,
    credentials: CredentialManager | None = None,
    profile: str = "default",
) -> InferenceProviderConfig:
    """Build a non-secret config for listing or selecting a provider."""
    base = active or InferenceProviderConfig()
    if provider_id == "ollama":
        resolved_base = _ollama_base_url(
            credentials or CredentialManager(),
            profile=profile,
            explicit=base_url,
            active=base,
        )
        return InferenceProviderConfig(
            type="openai-compatible",
            model=model or base.model or CATALOG_MODELS["ollama"][0],
            base_url=resolved_base,
            temperature=base.temperature,
            max_tokens=base.max_tokens,
            timeout_s=max(base.timeout_s, OLLAMA_DEFAULT_TIMEOUT_S),
            credential=base.credential,
        )
    if provider_id == "openai-compatible":
        return InferenceProviderConfig(
            type="openai-compatible",
            model=model or base.model or "llama3.2",
            base_url=base_url or base.base_url or OLLAMA_DEFAULT_BASE_URL,
            temperature=base.temperature,
            max_tokens=base.max_tokens,
            timeout_s=base.timeout_s,
            credential=base.credential,
        )
    kwargs: dict[str, Any] = {
        "type": "native",
        "vendor": provider_id,
        "model": model
        or (
            base.model
            if base.provider_id() == provider_id
            else CATALOG_MODELS.get(provider_id, ("default",))[0]
        ),
        "base_url": None,
        "temperature": base.temperature,
        "max_tokens": base.max_tokens,
        "timeout_s": base.timeout_s,
        "credential": base.credential,
        "api_version": base.api_version,
        "deployment": base.deployment,
        "azure_endpoint": base.azure_endpoint,
        "region": base.region,
        "aws_profile": base.aws_profile,
        "project": base.project,
        "organization": base.organization,
        "extra": dict(base.extra),
    }
    # Azure/Bedrock validators require fields — carry from active when switching to same family
    if provider_id == "azure_openai":
        kwargs["azure_endpoint"] = (
            base.azure_endpoint or base.base_url or "https://example.openai.azure.com"
        )
        kwargs["api_version"] = base.api_version or "2024-02-15-preview"
        kwargs["deployment"] = base.deployment or kwargs["model"]
        kwargs["base_url"] = None
    elif provider_id == "bedrock":
        kwargs["region"] = base.region or "us-east-1"
        kwargs["base_url"] = None
    elif provider_id == "openrouter":
        # Never inherit Ollama/local openai-compatible URLs — that yields 404s on
        # valid OpenRouter slugs like deepseek/deepseek-v4-flash-0731.
        kwargs["base_url"] = _resolve_openrouter_base_url(
            explicit=base_url,
            active=base if base.provider_id() == "openrouter" else None,
        )
    elif provider_id in {"openai", "anthropic", "google_genai", "groq"}:
        kwargs["base_url"] = base_url  # may be None; do not inherit foreign URLs
    return InferenceProviderConfig.model_validate(kwargs)


def _resolve_openrouter_base_url(
    *,
    explicit: str | None,
    active: InferenceProviderConfig | None,
) -> str:
    if explicit and not _looks_like_local_openai_compatible(explicit):
        return explicit.rstrip("/")
    if (
        active is not None
        and active.base_url
        and not _looks_like_local_openai_compatible(active.base_url)
    ):
        return active.base_url.rstrip("/")
    return OPENROUTER_DEFAULT_BASE_URL


def _looks_like_local_openai_compatible(url: str) -> bool:
    lower = url.strip().lower()
    return any(token in lower for token in LOCAL_INFERENCE_HOST_MARKERS)


def list_models_for_provider(
    credentials: CredentialManager,
    provider_id: str,
    *,
    active: InferenceProviderConfig,
    profile: str = "default",
    base_url: str | None = None,
) -> dict[str, Any]:
    eligible_ids = {p["providerId"] for p in eligible_providers(credentials, profile=profile)}
    if provider_id not in eligible_ids:
        raise ValueError(
            f"Provider {provider_id!r} has no credentials configured. "
            "Use /auth (Ctrl+K) to add keys first."
        )

    curated = list(CATALOG_MODELS.get(provider_id, ()))
    live: list[dict[str, Any]] = []
    source = "catalog"
    warning: str | None = None

    cfg = config_for_provider(
        provider_id,
        base_url=base_url,
        active=active,
        credentials=credentials,
        profile=profile,
    )
    cfg = cfg.model_copy(update={"timeout_s": min(cfg.timeout_s, 5.0)})
    try:
        from src.inference import build_inference

        mgr = build_inference(cfg, credentials, start=False)
        try:
            models = mgr.list_models()
            if models:
                live = [{"id": m.id, "ownedBy": m.owned_by} for m in models]
                source = "live"
        finally:
            mgr.close()
    except Exception as exc:  # noqa: BLE001
        warning = str(exc)

    # Curated first so preferred models stay within the TUI display window;
    # then live ids not already listed.
    models_out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for mid in curated:
        entry: dict[str, Any] = {"id": mid, "ownedBy": provider_id}
        label = CATALOG_MODEL_LABELS.get(mid)
        if label:
            entry["name"] = label
        models_out.append(entry)
        seen.add(mid)
    for m in live:
        mid = m["id"]
        if mid in seen:
            continue
        entry = dict(m)
        label = CATALOG_MODEL_LABELS.get(mid)
        if label and "name" not in entry:
            entry["name"] = label
        models_out.append(entry)
        seen.add(mid)

    return {
        "providerId": provider_id,
        "models": models_out,
        "source": source,
        "warning": warning,
    }


def apply_set_model(
    active: InferenceProviderConfig,
    params: dict[str, Any],
    credentials: CredentialManager,
    *,
    profile: str = "default",
) -> InferenceProviderConfig:
    provider_id = str(params.get("providerId") or "").strip()
    model = str(params.get("model") or "").strip()
    if not provider_id or not model:
        raise ValueError("providerId and model are required")
    eligible_ids = {p["providerId"] for p in eligible_providers(credentials, profile=profile)}
    if provider_id not in eligible_ids:
        raise ValueError(
            f"Provider {provider_id!r} has no credentials configured. "
            "Use /auth (Ctrl+K) to add keys first."
        )
    base_url = params.get("baseUrl")
    base_url_s = str(base_url) if base_url else None
    return config_for_provider(
        provider_id,
        model=model,
        base_url=base_url_s,
        active=active,
        credentials=credentials,
        profile=profile,
    )
