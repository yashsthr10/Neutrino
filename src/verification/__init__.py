"""Verification — lint/test runners for the coding agent."""

from __future__ import annotations

from src.verification.harness import (
    HarnessInfo,
    VerificationPolicy,
    build_verification_policy,
    detect_harness,
    probe_repo,
)
from src.verification.models import RunnerResult
from src.verification.runners import (
    VerificationPort,
    VerificationService,
    build_verification_service,
)

__all__ = [
    "HarnessInfo",
    "RunnerResult",
    "VerificationPolicy",
    "VerificationPort",
    "VerificationService",
    "build_verification_policy",
    "build_verification_service",
    "detect_harness",
    "probe_repo",
]
