"""L4 — Current task + working-set context."""

from __future__ import annotations

from typing import Any


def render_task_context(
    *,
    user_query: str,
    task_complexity: str | None = None,
    repo_path: str = "",
    code_changes: tuple[dict, ...] | list[dict] = (),
    plan_tasks: tuple[Any, ...] | list[Any] = (),
    repository_items: tuple[Any, ...] | list[Any] = (),
    checks_required: bool | None = None,
    policy_reason: str | None = None,
    harness: dict[str, Any] | None = None,
    test_results: dict[str, Any] | None = None,
    max_items: int = 24,
) -> str:
    lines = [
        "## CURRENT TASK",
        "",
        f"User request: {user_query.strip() or '(empty)'}",
    ]
    if task_complexity:
        lines.append(f"Task complexity: {task_complexity}")
    if repo_path:
        lines.append(f"Repository: `{repo_path}`")
    lines.append("")
    lines.append("## TASK CONTEXT")
    lines.append("")

    paths = _touched_paths(code_changes)
    if paths:
        lines.append("Files touched this run:")
        for p in paths[:40]:
            lines.append(f"- `{p}`")
        if len(paths) > 40:
            lines.append(f"- …and {len(paths) - 40} more")
    else:
        lines.append("Files touched this run: (none recorded yet)")

    if plan_tasks:
        lines.append("Checklist:")
        for t in list(plan_tasks)[:20]:
            if hasattr(t, "content"):
                status = getattr(t, "status", "pending")
                tid = getattr(t, "id", "")
                lines.append(f"- [{status}] {tid}: {t.content}".rstrip(": "))
            elif isinstance(t, dict):
                lines.append(
                    f"- [{t.get('status', 'pending')}] {t.get('id', '')}: "
                    f"{t.get('content', '')}".rstrip(": ")
                )

    items = list(repository_items)[:max_items]
    if items:
        lines.append("Working set (from context.resolve):")
        for item in items:
            kind = getattr(item, "kind", None) or (
                item.get("kind") if isinstance(item, dict) else "?"
            )
            payload = getattr(item, "payload", None)
            if payload is None and isinstance(item, dict):
                payload = item.get("payload")
            summary = _summarize_payload(kind, payload)
            lines.append(f"- ({kind}) {summary}")
    else:
        lines.append("Working set: not yet gathered — use `context.resolve` / `rna.*`.")

    if checks_required is None:
        lines.append("VERIFY policy: (not computed — call `verify.probe` if changing code)")
    elif checks_required:
        lines.append(
            f"VERIFY policy: checks **required** ({policy_reason or 'harness_present'})."
        )
    else:
        lines.append(
            f"VERIFY policy: checks **not required** ({policy_reason or 'waived'})."
        )

    if isinstance(harness, dict):
        lines.append(
            f"Harness: has_tests={harness.get('has_tests')}, "
            f"has_lint={harness.get('has_lint')}"
        )
    if isinstance(test_results, dict):
        lines.append(f"Last tests.run success: {test_results.get('success')}")

    lines.append("")
    return "\n".join(lines)


def _touched_paths(code_changes: tuple[dict, ...] | list[dict]) -> list[str]:
    paths: list[str] = []
    for change in code_changes:
        if not isinstance(change, dict):
            continue
        path = change.get("path") or change.get("file")
        if isinstance(path, str) and path.strip():
            paths.append(path.strip())
        elif isinstance(change.get("files"), list):
            for item in change["files"]:
                if isinstance(item, str):
                    paths.append(item)
                elif isinstance(item, dict) and isinstance(item.get("path"), str):
                    paths.append(item["path"])
    return list(dict.fromkeys(paths))


def _summarize_payload(kind: Any, payload: Any) -> str:
    if payload is None:
        return "(empty)"
    if isinstance(payload, dict):
        for key in ("path", "file", "name", "symbol", "query", "entrypoint"):
            val = payload.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()[:120]
        return str(list(payload.keys())[:6])[:120]
    if isinstance(payload, str):
        return payload[:120]
    return str(payload)[:120]
