"""GitHub-style +/- line preview for snippets."""


def unified_diff_preview(path: str, old_text: str, new_text: str, *, max_lines: int = 16) -> str:
    """Build a compact - / + block (path is only for callers that print a separate header)."""
    old_lines = old_text.splitlines()
    new_lines = new_text.splitlines()
    out: list[str] = ["---"]
    for line in old_lines[: max_lines // 2]:
        out.append(f"- {line}")
    if len(old_lines) > max_lines // 2:
        out.append("- ...")
    out.append("+++")
    for line in new_lines[: max_lines // 2]:
        out.append(f"+ {line}")
    if len(new_lines) > max_lines // 2:
        out.append("+ ...")
    return "\n".join(out)
