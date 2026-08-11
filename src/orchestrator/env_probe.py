"""Host-side environment snapshot for prompt Layer 3 (not inside src/agent)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from src.execution.git_service import GitService
from src.verification.harness import detect_harness


@dataclass(frozen=True, slots=True)
class EnvironmentSnapshot:
    working_directory: str
    repo_path: str
    is_git: bool = False
    branch: str | None = None
    git_status_summary: str | None = None
    dirty_paths: tuple[str, ...] = ()
    language: str | None = None
    has_tests: bool | None = None
    has_lint: bool | None = None
    test_evidence: tuple[str, ...] = ()
    lint_evidence: tuple[str, ...] = ()
    suggested_test_command: str | None = None
    suggested_lint_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def probe_environment(repo_path: Path, *, language: str | None = None) -> EnvironmentSnapshot:
    root = repo_path.resolve()
    git = GitService(root)
    is_git = (root / ".git").exists()
    branch: str | None = None
    summary: str | None = None
    dirty: tuple[str, ...] = ()
    if is_git:
        br = git.branch()
        if br.success:
            branch = str(br.data.get("branch") or "") or None
        st = git.status()
        if st.success:
            summary = str(st.data.get("summary") or "") or None
            raw = st.data.get("paths") or st.data.get("dirty_paths") or []
            dirty = tuple(str(p) for p in raw if p)[:40]

    harness = detect_harness(root)
    return EnvironmentSnapshot(
        working_directory=str(root),
        repo_path=str(root),
        is_git=is_git,
        branch=branch,
        git_status_summary=summary,
        dirty_paths=dirty,
        language=language,
        has_tests=harness.has_tests,
        has_lint=harness.has_lint,
        test_evidence=harness.test_evidence,
        lint_evidence=harness.lint_evidence,
        suggested_test_command=harness.suggested_test_command,
        suggested_lint_command=harness.suggested_lint_command,
    )
