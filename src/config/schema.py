"""Typed settings: model, CLI rules, session-facing config."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ProviderKind = Literal["langchain", "native", "ollama"]
RuntimeMode = Literal["fast", "deep", "auto"]
TUILayout = Literal["single", "split"]


class ModelConfig(BaseModel):
    provider: ProviderKind = "ollama"
    name: str = "llama3.2"
    ollama_base_url: str = "http://127.0.0.1:11434"
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)


class CliRules(BaseModel):
    verbose: bool = False
    dry_run: bool = False
    max_iterations: int = Field(default=25, ge=1, le=10_000)
    token_budget: int = Field(default=100_000, ge=1)
    runtime_mode: RuntimeMode = "fast"
    restrict_to_repo: bool = True
    layout: TUILayout = "single"


class NeutrinoSettings(BaseSettings):
    """Merged settings: env `NEUTRINO_*` with nested `NEUTRINO_MODEL__*` via delimiter."""

    model_config = SettingsConfigDict(
        env_prefix="NEUTRINO_",
        env_nested_delimiter="__",
        extra="ignore",
    )

    repo_path: Path = Field(default_factory=lambda: Path(".").resolve())
    model: ModelConfig = Field(default_factory=ModelConfig)
    rules: CliRules = Field(default_factory=CliRules)

    @field_validator("repo_path", mode="before")
    @classmethod
    def _path(cls, v: Path | str) -> Path:
        return Path(v).expanduser().resolve()
