"""Cache key construction."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CacheKey:
    repo_fingerprint: str
    subject_hash: str
    method_name: str
    params_hash: str
    tool_name: str
    tool_version: str

    def as_str(self) -> str:
        raw = "|".join(
            [
                self.repo_fingerprint,
                self.subject_hash,
                self.method_name,
                self.params_hash,
                self.tool_name,
                self.tool_version,
            ]
        )
        return hashlib.sha256(raw.encode()).hexdigest()


def params_hash(params: dict[str, Any]) -> str:
    payload = json.dumps(params, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:32]


def make_cache_key(
    *,
    repo_fingerprint: str,
    subject_hash: str,
    method_name: str,
    params: dict[str, Any],
    tool_name: str = "rna",
    tool_version: str = "1",
) -> CacheKey:
    return CacheKey(
        repo_fingerprint=repo_fingerprint,
        subject_hash=subject_hash,
        method_name=method_name,
        params_hash=params_hash(params),
        tool_name=tool_name,
        tool_version=tool_version,
    )
