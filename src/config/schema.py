"""Typed settings: inference, profiles, CLI rules."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderType = Literal["openai-compatible", "native"]
NativeVendor = Literal[
    "openai",
    "anthropic",
    "azure_openai",
    "bedrock",
    "google_genai",
    "groq",
    "openrouter",
]
# Legacy ModelConfig provider labels
LegacyProviderKind = Literal["langchain", "native", "ollama"]
RuntimeMode = Literal["fast", "deep", "auto"]
TUILayout = Literal["single", "split"]


class InferenceProviderConfig(BaseModel):
    """Non-secret inference settings. Secrets live in Credential Manager."""

    type: ProviderType = "openai-compatible"
    vendor: str | None = None
    model: str = "llama3.2"
    base_url: str | None = "http://127.0.0.1:11434/v1"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)
    max_tokens: int | None = None
    timeout_s: float = Field(default=60.0, gt=0)
    credential: str = "default"
    # Vendor extras (non-secret)
    api_version: str | None = None
    deployment: str | None = None
    azure_endpoint: str | None = None
    region: str | None = None
    aws_profile: str | None = None
    project: str | None = None
    organization: str | None = None
    extra: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_vendor_fields(self) -> InferenceProviderConfig:
        if self.type == "native":
            vendor = (self.vendor or "").lower()
            if vendor == "azure_openai":
                endpoint = self.azure_endpoint or self.base_url
                if not endpoint:
                    raise ValueError("azure_openai requires azure_endpoint or base_url")
                if not self.api_version:
                    raise ValueError("azure_openai requires api_version")
                if not (self.deployment or self.model):
                    raise ValueError("azure_openai requires deployment or model")
            if vendor == "bedrock" and not self.region:
                raise ValueError("bedrock requires region")
        return self

    def provider_id(self) -> str:
        if self.type == "openai-compatible":
            return "openai-compatible"
        return (self.vendor or "openai").lower()

    def config_hints(self) -> dict[str, str]:
        hints: dict[str, str] = {}
        if self.azure_endpoint:
            hints["azure_endpoint"] = self.azure_endpoint
        elif self.base_url and self.provider_id() == "azure_openai":
            hints["azure_endpoint"] = self.base_url
        if self.api_version:
            hints["api_version"] = self.api_version
        if self.deployment:
            hints["deployment"] = self.deployment
        if self.region:
            hints["region"] = self.region
        if self.aws_profile:
            hints["aws_profile"] = self.aws_profile
        if self.project:
            hints["project"] = self.project
        if self.organization:
            hints["organization"] = self.organization
        if self.base_url:
            hints["base_url"] = self.base_url
        return hints


class ModelConfig(BaseModel):
    """Deprecated legacy shape — prefer InferenceProviderConfig."""

    provider: LegacyProviderKind = "ollama"
    name: str = "llama3.2"
    ollama_base_url: str = "http://127.0.0.1:11434"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    def to_inference(self) -> InferenceProviderConfig:
        if self.provider == "ollama":
            base = self.ollama_base_url.rstrip("/")
            if not base.endswith("/v1"):
                base = f"{base}/v1"
            return InferenceProviderConfig(
                type="openai-compatible",
                model=self.name,
                base_url=base,
                temperature=self.temperature,
            )
        if self.provider == "native":
            return InferenceProviderConfig(
                type="native",
                vendor="openai",
                model=self.name,
                base_url=None,
                temperature=self.temperature,
            )
        # langchain → native openai default
        return InferenceProviderConfig(
            type="native",
            vendor="openai",
            model=self.name,
            base_url=None,
            temperature=self.temperature,
        )


class ProfileConfig(BaseModel):
    name: str
    inference: InferenceProviderConfig = Field(default_factory=InferenceProviderConfig)


class CliRules(BaseModel):
    verbose: bool = False
    dry_run: bool = False
    max_iterations: int = Field(default=25, ge=1, le=10_000)
    token_budget: int = Field(default=100_000, ge=1)
    max_verify_cycles: int = Field(
        default=2,
        ge=0,
        le=20,
        description="Bounded VERIFY -> EXECUTE retries when tests fail before hard-stopping.",
    )
    runtime_mode: RuntimeMode = "fast"
    restrict_to_repo: bool = True
    layout: TUILayout = "single"


class NeutrinoSettings(BaseSettings):
    """Merged settings: env `NEUTRINO_*` with nested `NEUTRINO_INFERENCE__*` via delimiter."""

    model_config = SettingsConfigDict(
        env_prefix="NEUTRINO_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    repo_path: Path = Field(default_factory=lambda: Path(".").resolve())
    inference: InferenceProviderConfig = Field(default_factory=InferenceProviderConfig)
    active_profile: str | None = None
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)
    # Kept for backward-compatible TOML/env; mirrored into inference when present.
    model: ModelConfig | None = None
    rules: CliRules = Field(default_factory=CliRules)

    @field_validator("repo_path", mode="before")
    @classmethod
    def _path(cls, v: Path | str) -> Path:
        return Path(v).expanduser().resolve()

    @model_validator(mode="before")
    @classmethod
    def _legacy_model_alias(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        # If only legacy model is provided, synthesize inference.
        if data.get("inference") is None and data.get("model") is not None:
            model = data["model"]
            if isinstance(model, ModelConfig):
                data["inference"] = model.to_inference()
            elif isinstance(model, dict):
                data["inference"] = ModelConfig.model_validate(model).to_inference()
        return data

    def resolved_inference(self) -> InferenceProviderConfig:
        if self.active_profile and self.active_profile in self.profiles:
            return self.profiles[self.active_profile].inference
        return self.inference
