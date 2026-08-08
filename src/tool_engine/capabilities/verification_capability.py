"""Verification capabilities — probe / tests / lint / review."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.tool_engine.capabilities.base import CapabilityBase
from src.tool_engine.models import ToolMeta, ToolResult
from src.verification.harness import probe_repo


class VerificationCapability(CapabilityBase):
    def as_handler_map(self) -> dict[str, Any]:
        return {
            "verify.probe": self.verify_probe,
            "tests.run": self.tests_run,
            "lint.run": self.lint_run,
            "review.run": self.review_run,
        }

    def verify_probe(self, *, max_paths: int = 80, **_: Any) -> ToolResult:
        root = self.services.repo_path
        if root is None:
            return ToolResult(
                success=False,
                data={},
                meta=ToolMeta(error="validation_error", reason="repo_path not configured"),
                errors=("repo_path not configured",),
            )
        data = probe_repo(Path(root), max_paths=int(max_paths or 80))
        return ToolResult(success=True, data=data, meta=ToolMeta())

    def tests_run(self, *, target: str | None = None, **_: Any) -> ToolResult:
        if self.services.verification is None:
            return self.serializer.not_implemented("tests.run")
        result = self.services.verification.run_tests(target=target)
        return ToolResult(
            success=result.success,
            data=result.to_dict(),
            meta=ToolMeta(
                error=None if result.success else "test_failed",
                truncated=result.truncated,
                reason=result.error,
            ),
            errors=() if result.success else (result.error or "tests failed",),
        )

    def lint_run(self, *, paths: list[str] | None = None, **_: Any) -> ToolResult:
        if self.services.verification is None:
            return self.serializer.not_implemented("lint.run")
        result = self.services.verification.run_lint(paths=paths)
        return ToolResult(
            success=result.success,
            data=result.to_dict(),
            meta=ToolMeta(
                error=None if result.success else "lint_failed",
                truncated=result.truncated,
                reason=result.error,
            ),
            errors=() if result.success else (result.error or "lint failed",),
        )

    def review_run(self, *, summary: str | None = None, **_: Any) -> ToolResult:
        _ = summary
        return self.serializer.not_implemented("review.run")
