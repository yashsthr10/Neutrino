"""Detect whether a repo has runnable test/lint checks, and when VERIFY can waive them."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# Paths that are not expected to be covered by unit/integration test harnesses.
_STATIC_SUFFIXES = frozenset(
    {
        ".html",
        ".htm",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".md",
        ".mdx",
        ".txt",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".webm",
        ".pdf",
    }
)

_TEST_MARKER_FILES = (
    "pytest.ini",
    "conftest.py",
    "tox.ini",
    "phpunit.xml",
    "phpunit.xml.dist",
    "jest.config.js",
    "jest.config.ts",
    "vitest.config.ts",
    "vitest.config.js",
    "karma.conf.js",
)

_LINT_MARKER_FILES = (
    ".eslintrc",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    "eslint.config.js",
    "eslint.config.mjs",
    ".rubocop.yml",
    "golangci.yml",
    ".golangci.yml",
)


@dataclass(frozen=True, slots=True)
class HarnessInfo:
    """What check tooling appears to exist in the repository."""

    has_tests: bool
    has_lint: bool
    test_evidence: tuple[str, ...] = ()
    lint_evidence: tuple[str, ...] = ()
    suggested_test_command: str | None = None
    suggested_lint_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class VerificationPolicy:
    """Runtime decision for the VERIFY phase gate."""

    checks_required: bool
    reason: str
    harness: HarnessInfo
    changed_paths: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "checks_required": self.checks_required,
            "reason": self.reason,
            "harness": self.harness.to_dict(),
            "changed_paths": list(self.changed_paths),
        }


def detect_harness(repo_root: Path | str) -> HarnessInfo:
    root = Path(repo_root).resolve()
    test_ev: list[str] = []
    lint_ev: list[str] = []
    test_cmd: str | None = None
    lint_cmd: str | None = None

    for name in _TEST_MARKER_FILES:
        if (root / name).is_file():
            test_ev.append(name)

    for name in _LINT_MARKER_FILES:
        if (root / name).is_file():
            lint_ev.append(name)

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = _read_text(pyproject)
        if "[tool.pytest" in text or "pytest" in text:
            test_ev.append("pyproject.toml:[tool.pytest]")
            test_cmd = test_cmd or "pytest"
        if "[tool.ruff" in text or "ruff" in text:
            lint_ev.append("pyproject.toml:[tool.ruff]")
            lint_cmd = lint_cmd or "ruff check"
        if "[tool.mypy" in text:
            lint_ev.append("pyproject.toml:[tool.mypy]")

    setup_cfg = root / "setup.cfg"
    if setup_cfg.is_file() and "pytest" in _read_text(setup_cfg).lower():
        test_ev.append("setup.cfg:pytest")
        test_cmd = test_cmd or "pytest"

    package_json = root / "package.json"
    if package_json.is_file():
        scripts = _package_scripts(package_json)
        if "test" in scripts:
            test_ev.append("package.json:scripts.test")
            test_cmd = test_cmd or "npm test"
        if "lint" in scripts:
            lint_ev.append("package.json:scripts.lint")
            lint_cmd = lint_cmd or "npm run lint"

    makefile = root / "Makefile"
    if makefile.is_file():
        mk = _read_text(makefile)
        if _makefile_has_target(mk, "test"):
            test_ev.append("Makefile:test")
            test_cmd = test_cmd or "make test"
        if _makefile_has_target(mk, "lint"):
            lint_ev.append("Makefile:lint")
            lint_cmd = lint_cmd or "make lint"

    if (root / "Cargo.toml").is_file():
        test_ev.append("Cargo.toml")
        test_cmd = test_cmd or "cargo test"
    if (root / "go.mod").is_file():
        test_ev.append("go.mod")
        test_cmd = test_cmd or "go test ./..."

    # Directory / file heuristics (bounded walk).
    if _has_tests_tree(root):
        test_ev.append("tests/ or test_*.py / *_test.go")
        test_cmd = test_cmd or "pytest"

    if (root / "ruff.toml").is_file() or (root / ".ruff.toml").is_file():
        lint_ev.append("ruff.toml")
        lint_cmd = lint_cmd or "ruff check"

    # Dedupe while preserving order
    test_ev = list(dict.fromkeys(test_ev))
    lint_ev = list(dict.fromkeys(lint_ev))

    return HarnessInfo(
        has_tests=bool(test_ev),
        has_lint=bool(lint_ev),
        test_evidence=tuple(test_ev),
        lint_evidence=tuple(lint_ev),
        suggested_test_command=test_cmd if test_ev else None,
        suggested_lint_command=lint_cmd if lint_ev else None,
    )


def changed_paths_from_code_changes(code_changes: tuple[dict, ...] | list[dict]) -> tuple[str, ...]:
    paths: list[str] = []
    for change in code_changes:
        if not isinstance(change, dict):
            continue
        for key in ("path", "file", "filename"):
            val = change.get(key)
            if isinstance(val, str) and val.strip():
                paths.append(val.strip())
        files = change.get("files") or change.get("paths")
        if isinstance(files, (list, tuple)):
            for item in files:
                if isinstance(item, str) and item.strip():
                    paths.append(item.strip())
                elif isinstance(item, dict):
                    p = item.get("path") or item.get("file")
                    if isinstance(p, str) and p.strip():
                        paths.append(p.strip())
    return tuple(dict.fromkeys(paths))


def is_static_path(path: str) -> bool:
    suffix = Path(path).suffix.lower()
    return suffix in _STATIC_SUFFIXES


def build_verification_policy(
    repo_root: Path | str,
    *,
    code_changes: tuple[dict, ...] | list[dict] = (),
    user_query: str = "",
) -> VerificationPolicy:
    """Decide whether VERIFY must run tests/lint before DONE."""
    harness = detect_harness(repo_root)
    paths = changed_paths_from_code_changes(code_changes)
    query = (user_query or "").lower()

    if paths and all(is_static_path(p) for p in paths):
        return VerificationPolicy(
            checks_required=False,
            reason="static_assets_only",
            harness=harness,
            changed_paths=paths,
        )

    # Explicit content-only intents when we have no code-change paths yet.
    if not paths and any(
        phrase in query
        for phrase in (
            "landing page",
            "static page",
            "html page",
            "readme only",
            "markdown only",
        )
    ):
        return VerificationPolicy(
            checks_required=False,
            reason="content_task_no_code_changes",
            harness=harness,
            changed_paths=paths,
        )

    if not harness.has_tests and not harness.has_lint:
        return VerificationPolicy(
            checks_required=False,
            reason="no_test_or_lint_harness",
            harness=harness,
            changed_paths=paths,
        )

    if harness.has_tests:
        return VerificationPolicy(
            checks_required=True,
            reason="test_harness_present",
            harness=harness,
            changed_paths=paths,
        )

    # Lint-only harness still counts as a required check when code changed.
    return VerificationPolicy(
        checks_required=True,
        reason="lint_harness_present",
        harness=harness,
        changed_paths=paths,
    )


def probe_repo(repo_root: Path | str, *, max_paths: int = 80) -> dict[str, Any]:
    """Structured VERIFY helper: harness + shallow path sample (ls-like)."""
    root = Path(repo_root).resolve()
    harness = detect_harness(root)
    sample = _sample_paths(root, limit=max_paths)
    return {
        "repo_root": str(root),
        "harness": harness.to_dict(),
        "sample_paths": sample,
        "path_count_sampled": len(sample),
        "guidance": (
            "Run tests.run / lint.run when harness markers exist and changes are code. "
            "If checks_required is false for this task, emit a short final; "
            "the runtime will advance without a green tests.run."
        ),
    }


def _sample_paths(root: Path, *, limit: int) -> list[str]:
    ignore_dirs = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".rna_cache",
        ".context_cache",
        "dist",
        "build",
        ".next",
        "target",
        ".cursor",
    }
    out: list[str] = []
    try:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if any(part in ignore_dirs for part in rel.parts):
                continue
            out.append(rel.as_posix())
            if len(out) >= limit:
                break
    except OSError:
        return out
    return out


def _has_tests_tree(root: Path) -> bool:
    for candidate in (root / "tests", root / "test"):
        if candidate.is_dir():
            return True
    # Shallow fallback only — avoid full-repo rglob on large checkouts.
    try:
        for child in root.iterdir():
            if child.is_file() and (child.name.startswith("test_") and child.suffix == ".py"):
                return True
            if child.is_dir() and child.name not in {
                ".git",
                "node_modules",
                ".venv",
                "venv",
                "vendor",
            }:
                for nested in child.iterdir():
                    if nested.is_file() and (
                        (nested.name.startswith("test_") and nested.suffix == ".py")
                        or nested.name.endswith("_test.go")
                    ):
                        return True
    except OSError:
        return False
    return False


def _package_scripts(package_json: Path) -> dict[str, str]:
    try:
        data = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    scripts = data.get("scripts") if isinstance(data, dict) else None
    if not isinstance(scripts, dict):
        return {}
    return {str(k): str(v) for k, v in scripts.items()}


def _makefile_has_target(text: str, name: str) -> bool:
    for line in text.splitlines():
        if line.startswith(f"{name}:") or line.startswith(f"{name} :"):
            return True
    return False


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
