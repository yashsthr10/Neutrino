"""Environment-variable credential overlays."""

from __future__ import annotations

import os

from src.credentials.models import CredentialRecord

# provider_id -> ordered (env_var, field_name) mappings
ENV_MAP: dict[str, tuple[tuple[str, str], ...]] = {
    "openai": (("OPENAI_API_KEY", "api_key"),),
    "anthropic": (("ANTHROPIC_API_KEY", "api_key"),),
    "azure_openai": (("AZURE_OPENAI_API_KEY", "api_key"),),
    "bedrock": (
        ("AWS_ACCESS_KEY_ID", "access_key_id"),
        ("AWS_SECRET_ACCESS_KEY", "secret_access_key"),
        ("AWS_SESSION_TOKEN", "session_token"),
    ),
    "google_genai": (("GOOGLE_API_KEY", "api_key"), ("GEMINI_API_KEY", "api_key")),
    "groq": (("GROQ_API_KEY", "api_key"),),
    "openrouter": (("OPENROUTER_API_KEY", "api_key"),),
    "openai-compatible": (("NEUTRINO_INFERENCE_API_KEY", "api_key"),),
}

KIND_FOR_PROVIDER: dict[str, str] = {
    "openai": "api_key",
    "anthropic": "api_key",
    "azure_openai": "azure",
    "bedrock": "aws",
    "google_genai": "api_key",
    "groq": "api_key",
    "openrouter": "api_key",
    "openai-compatible": "api_key",
}


def read_env_record(provider_id: str) -> CredentialRecord | None:
    mapping = ENV_MAP.get(provider_id)
    if not mapping:
        return None
    fields: dict[str, str] = {}
    for env_name, field_name in mapping:
        value = os.environ.get(env_name)
        if value and field_name not in fields:
            fields[field_name] = value
    if provider_id == "bedrock":
        if "access_key_id" in fields and "secret_access_key" in fields:
            return CredentialRecord(kind="aws", fields=fields)
        return None
    if provider_id == "azure_openai":
        if "api_key" in fields:
            return CredentialRecord(kind="azure", fields=fields)
        return None
    if "api_key" in fields:
        return CredentialRecord(kind="api_key", fields=fields)
    return None


def env_config_hints(provider_id: str) -> dict[str, str]:
    """Non-secret hints that may appear in env (endpoint/region)."""
    hints: dict[str, str] = {}
    if provider_id == "azure_openai":
        endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
        if endpoint:
            hints["azure_endpoint"] = endpoint
        version = os.environ.get("AZURE_OPENAI_API_VERSION")
        if version:
            hints["api_version"] = version
    if provider_id == "bedrock":
        region = os.environ.get("AWS_DEFAULT_REGION") or os.environ.get("AWS_REGION")
        if region:
            hints["region"] = region
    if provider_id == "openai":
        org = os.environ.get("OPENAI_ORG_ID")
        if org:
            hints["organization"] = org
    return hints
