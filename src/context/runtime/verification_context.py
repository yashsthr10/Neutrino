"""VerificationContext — test results and reviewer feedback owned by Verifier."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class VerificationContext:
    test_results: dict | None = None
    reviewer_feedback: dict | None = None
    # Runtime VERIFY policy (from harness + changed paths). None until computed.
    checks_required: bool | None = None
    policy_reason: str | None = None
    harness: dict | None = None
