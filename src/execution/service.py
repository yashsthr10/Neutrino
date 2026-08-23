"""ExecutionService — apply edits, diff, rollback, shell. Tool Engine calls this via ports."""

from __future__ import annotations

import difflib
import uuid
from pathlib import Path
from typing import Protocol, runtime_checkable

from src.execution import editblock, patch_format, udiff
from src.execution.models import (
    ApplyFailure,
    ApplyResult,
    ChangeRecord,
    EditFormat,
    FileChange,
    ShellResult,
)
from src.execution.paths import PathSecurityError, resolve_repo_path
from src.execution.shell import run_shell, run_terminal


@runtime_checkable
class ExecutionPort(Protocol):
    def apply(
        self,
        *,
        patch: str = "",
        path: str | None = None,
        format: EditFormat | str = "auto",
        dry_run: bool = False,
    ) -> ApplyResult: ...

    def diff(self, *, path: str | None = None, change_id: str | None = None) -> dict: ...

    def rollback(self, *, change_id: str | None = None) -> dict: ...

    def run(
        self,
        *,
        command: str,
        approved: bool = False,
        timeout_s: float = 120.0,
    ) -> ShellResult: ...

    def terminal(
        self,
        *,
        command: str,
        approved: bool = False,
        timeout_s: float = 600.0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ) -> ShellResult: ...


class ExecutionService:
    """Repo-scoped file edit apply + shell. No LLM calls."""

    def __init__(self, repo_root: Path) -> None:
        self.repo_root = repo_root.resolve()
        self._history: dict[str, ChangeRecord] = {}
        self._last_change_id: str | None = None

    def apply(
        self,
        *,
        patch: str = "",
        path: str | None = None,
        format: EditFormat | str = "auto",
        dry_run: bool = False,
    ) -> ApplyResult:
        if not patch.strip():
            return ApplyResult(
                success=False,
                format=str(format),
                dry_run=dry_run,
                change_id=None,
                errors=("empty patch",),
                reflection="Provide a non-empty patch / SEARCH-REPLACE / udiff payload.",
            )

        fmt = self._detect_format(patch, format)
        try:
            if fmt == "patch":
                return self._apply_patch(patch, dry_run=dry_run)
            if fmt == "search_replace":
                return self._apply_search_replace(patch, dry_run=dry_run)
            if fmt == "udiff":
                return self._apply_udiff(patch, dry_run=dry_run)
        except (PathSecurityError, patch_format.DiffError, ValueError) as exc:
            return ApplyResult(
                success=False,
                format=fmt,
                dry_run=dry_run,
                change_id=None,
                errors=(str(exc),),
                reflection=str(exc),
            )
        return ApplyResult(
            success=False,
            format=str(format),
            dry_run=dry_run,
            change_id=None,
            errors=(f"unsupported format: {format}",),
        )

    def diff(self, *, path: str | None = None, change_id: str | None = None) -> dict:
        cid = change_id or self._last_change_id
        if cid is None or cid not in self._history:
            # Fall back to working-tree vs recorded last apply: show live file diffs
            # against empty history — return empty pending.
            return {"change_id": cid, "diffs": [], "note": "no tracked change"}
        record = self._history[cid]
        diffs = []
        for ch in record.changes:
            if path and ch.path != path:
                continue
            before = (ch.before or "").splitlines(keepends=True)
            after = (ch.after or "").splitlines(keepends=True)
            text = "".join(
                difflib.unified_diff(
                    before,
                    after,
                    fromfile=f"a/{ch.path}",
                    tofile=f"b/{ch.path}",
                )
            )
            diffs.append({"path": ch.path, "action": ch.action, "diff": text})
        return {"change_id": cid, "diffs": diffs}

    def rollback(self, *, change_id: str | None = None) -> dict:
        cid = change_id or self._last_change_id
        if cid is None or cid not in self._history:
            return {"success": False, "error": "unknown change_id", "change_id": cid}
        record = self._history[cid]
        restored: list[str] = []
        errors: list[str] = []
        # Reverse order for safe restore
        for ch in reversed(record.changes):
            try:
                abs_path = resolve_repo_path(self.repo_root, ch.path)
                if ch.action == "add":
                    if abs_path.exists():
                        abs_path.unlink()
                    restored.append(ch.path)
                elif ch.action == "delete":
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(ch.before or "", encoding="utf-8")
                    restored.append(ch.path)
                else:
                    abs_path.write_text(ch.before or "", encoding="utf-8")
                    restored.append(ch.path)
            except (OSError, PathSecurityError) as exc:
                errors.append(f"{ch.path}: {exc}")
        del self._history[cid]
        if self._last_change_id == cid:
            self._last_change_id = None
        return {
            "success": not errors,
            "change_id": cid,
            "restored": restored,
            "errors": errors,
        }

    def run(
        self,
        *,
        command: str,
        approved: bool = False,
        timeout_s: float = 120.0,
    ) -> ShellResult:
        return run_shell(
            command,
            cwd=self.repo_root,
            timeout_s=timeout_s,
            approved=approved,
        )

    def terminal(
        self,
        *,
        command: str,
        approved: bool = False,
        timeout_s: float = 600.0,
        cwd: str | None = None,
        env: dict[str, str] | None = None,
        stdin: str | None = None,
    ) -> ShellResult:
        return run_terminal(
            command,
            repo_root=self.repo_root,
            cwd=cwd,
            env=env,
            stdin=stdin,
            timeout_s=timeout_s,
            approved=approved,
        )

    def _detect_format(self, patch: str, format: EditFormat | str) -> str:
        if format and format != "auto":
            return str(format)
        if patch_format.looks_like_patch(patch):
            return "patch"
        if editblock.looks_like_search_replace(patch):
            return "search_replace"
        if udiff.looks_like_udiff(patch):
            return "udiff"
        # Prefer search_replace if path-like SEARCH markers absent but --- present
        return "patch" if "***" in patch else "search_replace"

    def _apply_patch(self, text: str, *, dry_run: bool) -> ApplyResult:
        needed = patch_format.identify_files_needed(text)
        current: dict[str, str] = {}
        for rel in needed:
            abs_path = resolve_repo_path(self.repo_root, rel)
            if not abs_path.exists():
                raise patch_format.DiffError(f"File referenced in patch not found: {rel}")
            current[rel] = abs_path.read_text(encoding="utf-8")

        parsed = patch_format.parse_patch_text(text, current)
        changes: list[FileChange] = []
        failures: list[ApplyFailure] = []

        for path, action in parsed.actions.items():
            abs_path = resolve_repo_path(self.repo_root, path)
            try:
                if action.type == patch_format.ActionType.ADD:
                    if abs_path.exists():
                        raise patch_format.DiffError(f"ADD Error: File already exists: {path}")
                    content = action.new_content or ""
                    if not content.endswith("\n"):
                        content += "\n"
                    changes.append(FileChange(path=path, action="add", before=None, after=content))
                elif action.type == patch_format.ActionType.DELETE:
                    before = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
                    changes.append(
                        FileChange(path=path, action="delete", before=before, after=None)
                    )
                else:
                    before = abs_path.read_text(encoding="utf-8")
                    after = patch_format.apply_update_content(before, action)
                    target = action.move_path or path
                    if action.move_path:
                        changes.append(
                            FileChange(path=path, action="delete", before=before, after=None)
                        )
                        changes.append(
                            FileChange(path=target, action="add", before=None, after=after)
                        )
                    else:
                        changes.append(
                            FileChange(path=path, action="update", before=before, after=after)
                        )
            except patch_format.DiffError as exc:
                failures.append(ApplyFailure(path=path, reason=str(exc)))

        return self._finalize(changes, failures, format="patch", dry_run=dry_run)

    def _apply_search_replace(self, text: str, *, dry_run: bool) -> ApplyResult:
        try:
            blocks = list(editblock.find_original_update_blocks(text))
        except ValueError as exc:
            return ApplyResult(
                success=False,
                format="search_replace",
                dry_run=dry_run,
                change_id=None,
                errors=(str(exc),),
                reflection=str(exc),
            )

        # Group by path preserving order
        pending: dict[str, list[tuple[str, str]]] = {}
        order: list[str] = []
        for item in blocks:
            if len(item) == 2 and item[0] is None:
                continue  # skip shell fences in apply path
            path, before, after = item  # type: ignore[misc]
            if path not in pending:
                pending[path] = []
                order.append(path)
            pending[path].append((before, after))

        changes: list[FileChange] = []
        failures: list[ApplyFailure] = []
        for path in order:
            abs_path = resolve_repo_path(self.repo_root, path)
            content = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
            original = content
            path_failures: list[ApplyFailure] = []
            for before, after in pending[path]:
                new_content = editblock.apply_search_replace(content, before, after, fname=path)
                if new_content is None:
                    similar = editblock.find_similar_lines(before, content)
                    path_failures.append(
                        ApplyFailure(
                            path=path,
                            reason="SEARCH block did not match file contents",
                            search=before[:2000],
                            similar=similar or None,
                        )
                    )
                else:
                    content = new_content
            if path_failures:
                failures.extend(path_failures)
            elif content != original or not abs_path.exists():
                action = "add" if not abs_path.exists() and not original else "update"
                changes.append(
                    FileChange(
                        path=path,
                        action=action,  # type: ignore[arg-type]
                        before=original if abs_path.exists() else None,
                        after=content,
                    )
                )

        reflection = None
        if failures:
            parts = ["Apply failed for SEARCH/REPLACE blocks. Retry with exact file context."]
            for f in failures:
                parts.append(f"\n## {f.path}\n{f.reason}")
                if f.similar:
                    parts.append(f"\nDid you mean:\n```\n{f.similar}\n```")
            reflection = "\n".join(parts)

        return self._finalize(
            changes, failures, format="search_replace", dry_run=dry_run, reflection=reflection
        )

    def _apply_udiff(self, text: str, *, dry_run: bool) -> ApplyResult:
        raw = udiff.find_diffs(text)
        if not raw:
            return ApplyResult(
                success=False,
                format="udiff",
                dry_run=dry_run,
                change_id=None,
                errors=("no udiff hunks found",),
                reflection="Provide a ```diff fenced unified diff with --- / +++ headers.",
            )

        last_path: str | None = None
        by_path: dict[str, list[list[str]]] = {}
        order: list[str] = []
        for path, hunk in raw:
            if path:
                last_path = path
            else:
                path = last_path
            if not path:
                continue
            hunk = udiff.normalize_hunk(hunk)
            if not hunk:
                continue
            if path not in by_path:
                by_path[path] = []
                order.append(path)
            by_path[path].append(hunk)

        changes: list[FileChange] = []
        failures: list[ApplyFailure] = []
        for path in order:
            abs_path = resolve_repo_path(self.repo_root, path)
            content = abs_path.read_text(encoding="utf-8") if abs_path.exists() else ""
            original = content
            for hunk in by_path[path]:
                before, _after = udiff.hunk_to_before_after(hunk)
                try:
                    new_content = udiff.apply_hunk_to_content(content, hunk)
                except udiff.SearchTextNotUnique:
                    failures.append(
                        ApplyFailure(
                            path=path,
                            reason="hunk matched multiple locations; add more context",
                            search=before[:2000],
                        )
                    )
                    new_content = None
                if new_content is None:
                    failures.append(
                        ApplyFailure(
                            path=path,
                            reason="hunk failed to apply",
                            search=before[:2000],
                            similar=editblock.find_similar_lines(before, content) or None,
                        )
                    )
                else:
                    content = new_content
            if not any(f.path == path for f in failures) and content != original:
                changes.append(
                    FileChange(
                        path=path,
                        action="update" if abs_path.exists() else "add",
                        before=original if abs_path.exists() else None,
                        after=content,
                    )
                )

        reflection = None
        if failures:
            reflection = (
                "Unified diff hunks failed. Re-send with exact context lines from the file."
            )

        return self._finalize(
            changes, failures, format="udiff", dry_run=dry_run, reflection=reflection
        )

    def _finalize(
        self,
        changes: list[FileChange],
        failures: list[ApplyFailure],
        *,
        format: str,
        dry_run: bool,
        reflection: str | None = None,
    ) -> ApplyResult:
        if failures and not changes:
            return ApplyResult(
                success=False,
                format=format,
                dry_run=dry_run,
                change_id=None,
                failures=tuple(failures),
                reflection=reflection,
                errors=tuple(f.reason for f in failures),
            )

        change_id = None
        if not dry_run and changes and not failures:
            for ch in changes:
                abs_path = resolve_repo_path(self.repo_root, ch.path)
                if ch.action == "delete":
                    if abs_path.exists():
                        abs_path.unlink()
                else:
                    abs_path.parent.mkdir(parents=True, exist_ok=True)
                    abs_path.write_text(ch.after or "", encoding="utf-8")
            change_id = uuid.uuid4().hex[:12]
            self._history[change_id] = ChangeRecord(change_id=change_id, changes=list(changes))
            self._last_change_id = change_id
        elif dry_run and changes and not failures:
            change_id = f"dry-{uuid.uuid4().hex[:8]}"

        success = bool(changes) and not failures
        if failures and changes:
            # Partial success — do not write if any failure (atomic per invoke)
            success = False
            if not dry_run:
                # We skipped write when failures present
                pass
            reflection = reflection or (
                "Some edits failed; no files were written. Fix failures and retry."
            )

        # Write only when fully successful (already handled above). If partial, ensure no write.
        if not dry_run and changes and failures:
            change_id = None

        return ApplyResult(
            success=success,
            format=format,
            dry_run=dry_run,
            change_id=change_id,
            changes=tuple(changes),
            failures=tuple(failures),
            reflection=reflection,
            errors=tuple(f.reason for f in failures),
        )


def build_execution_service(repo_root: Path | str) -> ExecutionService:
    return ExecutionService(Path(repo_root))
