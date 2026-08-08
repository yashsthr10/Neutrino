"""Re-export inference config from src.config (single source of truth)."""

from src.config.schema import InferenceProviderConfig

__all__ = ["InferenceProviderConfig"]
