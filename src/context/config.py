"""Context Subsystem configuration (standalone pydantic BaseModel)."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class ContextConfig(BaseModel):
    """Configuration for Context Manager and Conversation Manager."""

    cache_dir: Path | None = None
    max_context_tokens: int = Field(default=8_000, ge=1)
    max_files: int = Field(default=5, ge=1)
    max_lines_per_file: int = Field(default=200, ge=1)
    conversation_reserve_ratio: float = Field(default=0.25, ge=0.0, le=1.0)
    summarization_trigger_tokens: int = Field(default=3_000, ge=1)
    decision_extraction_llm_enabled: bool = False
    memory_embedding_model: str = "hash"  # "hash" | "sentence-transformers"
    l1_cache_size: int = Field(default=256, ge=1)
    cache_enabled: bool = True
    retrieval_timeout_ms: int = Field(default=5_000, ge=100)

    # Ranker weights (03_context_composition.md S5)
    w_hint: float = Field(default=0.40, ge=0.0)
    w_confidence: float = Field(default=0.20, ge=0.0)
    w_recency: float = Field(default=0.15, ge=0.0)
    w_relation: float = Field(default=0.15, ge=0.0)
    w_distance: float = Field(default=0.10, ge=0.0)

    @field_validator("cache_dir", mode="before")
    @classmethod
    def _resolve_cache(cls, v: Path | str | None) -> Path | None:
        if v is None:
            return None
        return Path(v).expanduser().resolve()

    def resolved_cache_dir(self, repo_path: Path | None = None) -> Path:
        if self.cache_dir is not None:
            return self.cache_dir
        if repo_path is not None:
            return Path(repo_path).resolve() / ".context_cache"
        return Path(".context_cache").resolve()
