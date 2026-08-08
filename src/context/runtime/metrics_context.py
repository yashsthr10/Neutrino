"""MetricsContext — token usage and per-stage cost."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class MetricsContext:
    token_usage_used: int = 0
    token_usage_budget: int | None = None
    cost_ms_by_stage: dict[str, float] = field(default_factory=dict)
