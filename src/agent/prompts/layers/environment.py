"""L3 — Dynamic environment section."""

from __future__ import annotations

from typing import Any


def render_environment(env: dict[str, Any] | None) -> str:
    if not env:
        return "## ENVIRONMENT\n\n(not probed yet)\n"

    lines = ["## ENVIRONMENT", ""]
    wd = env.get("working_directory") or env.get("repo_path")
    if wd:
        lines.append(f"Working directory: `{wd}`")
    if env.get("is_git") is True:
        lines.append("Repository: git repository")
    elif env.get("is_git") is False:
        lines.append("Repository: not a git checkout")
    branch = env.get("branch")
    if branch:
        lines.append(f"Branch: `{branch}`")
    status = env.get("git_status_summary")
    if status:
        lines.append(f"Git status: {status}")
    dirty = env.get("dirty_paths") or ()
    if dirty:
        lines.append("Dirty paths:")
        for p in list(dirty)[:20]:
            lines.append(f"- `{p}`")
        if len(dirty) > 20:
            lines.append(f"- …and {len(dirty) - 20} more")
    lang = env.get("language")
    if lang:
        lines.append(f"Language: {lang}")
    if env.get("has_tests") is not None or env.get("has_lint") is not None:
        lines.append(
            f"Harness: has_tests={env.get('has_tests')}, has_lint={env.get('has_lint')}"
        )
    te = env.get("test_evidence") or ()
    if te:
        lines.append("Test evidence: " + ", ".join(str(x) for x in list(te)[:8]))
    le = env.get("lint_evidence") or ()
    if le:
        lines.append("Lint evidence: " + ", ".join(str(x) for x in list(le)[:8]))
    cmd = env.get("suggested_test_command")
    if cmd:
        lines.append(f"Suggested test command: `{cmd}`")
    lcmd = env.get("suggested_lint_command")
    if lcmd:
        lines.append(f"Suggested lint command: `{lcmd}`")
    lines.append("")
    return "\n".join(lines)
