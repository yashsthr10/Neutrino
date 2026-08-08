"""RNA configuration (standalone pydantic BaseModel — embeddable, no env binding required)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, field_validator

TierName = Literal["structural", "semantic", "whole_program"]


class RnaConfig(BaseModel):
    """Configuration for an Rna instance."""

    repo_path: Path
    cache_dir: Path | None = None
    enabled_tiers: tuple[TierName, ...] = ("structural", "semantic", "whole_program")
    ignore_patterns: tuple[str, ...] = (
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".rna_cache",
        ".context_cache",
        "dist",
        "build",
        ".next",
        "target",
        "*.pyc",
        "*.pyo",
        "*.so",
        "*.egg-info",
    )
    max_lines_per_file: int = Field(default=200, ge=1)
    max_search_results: int = Field(default=50, ge=1)
    max_callers: int = Field(default=25, ge=1)
    max_workflow_depth: int = Field(default=6, ge=1, le=6)
    lsp_timeout_ms: int = Field(default=5000, ge=100)
    tier3_timeout_ms: int = Field(default=30000, ge=100)
    web_search_enabled: bool = False
    web_search_provider: str = "google_cse"
    web_search_api_key: str | None = None
    web_search_cx: str | None = None
    web_cache_ttl_seconds: int = Field(default=86_400, ge=0)
    log_web_query_text: bool = False
    embedding_model: str = "hash"  # "hash" (offline default) | "sentence-transformers"
    l1_cache_size: int = Field(default=256, ge=1)
    cache_enabled: bool = True

    @field_validator("repo_path", mode="before")
    @classmethod
    def _resolve_repo(cls, v: Path | str) -> Path:
        return Path(v).expanduser().resolve()

    @field_validator("cache_dir", mode="before")
    @classmethod
    def _resolve_cache(cls, v: Path | str | None) -> Path | None:
        if v is None:
            return None
        return Path(v).expanduser().resolve()

    def resolved_cache_dir(self) -> Path:
        if self.cache_dir is not None:
            return self.cache_dir
        return self.repo_path / ".rna_cache"
