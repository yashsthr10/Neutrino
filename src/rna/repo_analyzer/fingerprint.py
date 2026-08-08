"""Repo and file content hashing for cache keys."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def content_hash(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8", errors="replace")
    return hashlib.sha256(data).hexdigest()


def file_content_hash(path: Path) -> str:
    try:
        return content_hash(path.read_bytes())
    except OSError:
        return content_hash(b"")


def repo_fingerprint(repo_path: Path) -> str:
    """
    Current git commit SHA if the tree is clean; otherwise a hash of
    status porcelain plus content hashes of dirty files.
    """
    repo_path = repo_path.resolve()
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=5,
        )
        if head.returncode != 0:
            return _fallback_fingerprint(repo_path)
        commit = head.stdout.strip()
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        if status.returncode != 0 or not status.stdout.strip():
            return commit
        dirty_parts = [commit, status.stdout]
        for line in status.stdout.splitlines():
            # XY PATH or XY ORIG -> PATH
            path_part = line[3:].strip()
            if " -> " in path_part:
                path_part = path_part.split(" -> ", 1)[1]
            fpath = repo_path / path_part
            if fpath.is_file():
                dirty_parts.append(f"{path_part}:{file_content_hash(fpath)}")
        return content_hash("|".join(dirty_parts))
    except (OSError, subprocess.TimeoutExpired):
        return _fallback_fingerprint(repo_path)


def _fallback_fingerprint(repo_path: Path) -> str:
    hasher = hashlib.sha256()
    count = 0
    for p in sorted(repo_path.rglob("*")):
        if not p.is_file():
            continue
        if any(part.startswith(".") for part in p.relative_to(repo_path).parts):
            continue
        try:
            rel = str(p.relative_to(repo_path))
            st = p.stat()
            hasher.update(f"{rel}:{st.st_mtime_ns}:{st.st_size}".encode())
            count += 1
            if count >= 5000:
                break
        except OSError:
            continue
    return hasher.hexdigest()
