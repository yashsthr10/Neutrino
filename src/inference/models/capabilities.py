"""Provider capability flags."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ProviderCapabilities:
    tools: bool = False
    structured_output: bool = False
    streaming: bool = True
