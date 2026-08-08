"""Health-check helpers."""

from __future__ import annotations

from src.inference.errors import InferenceConnectionError
from src.inference.models.response import HealthStatus
from src.inference.providers.base import InferenceProvider


def ensure_healthy(provider: InferenceProvider) -> HealthStatus:
    status = provider.health()
    if not status.ok:
        raise InferenceConnectionError(status.message or "health check failed")
    return status
