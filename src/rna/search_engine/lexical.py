"""ripgrep-backed lexical search with Python re fallback."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from src.rna.models import SearchHit
from src.rna.repo_analyzer.tree import RepoTree

# Common bundled locations (e.g. Cursor's shipped rg)
_EXTRA_RG_PATHS = (
    "/usr/share/cursor/resources/app/node_modules/@vscode/ripgrep/bin/rg",
    "/usr/lib/node_modules/@vscode/ripgrep/bin/rg",
)


def find_rg() -> str | None:
    found = shutil.which("rg")
    if found:
        return found
    for candidate in _EXTRA_RG_PATHS:
        p = Path(candidate)
        if p.is_file() and os_access_exec(p):
            return str(p)
    return None


def os_access_exec(p: Path) -> bool:
    try:
        return p.exists()
    except OSError:
        return False


class LexicalSearch:
    def __init__(self, root: Path, tree: RepoTree) -> None:
        self.root = root.resolve()
        self.tree = tree
        self._rg = find_rg()

    def search(
        self,
        query: str,
        *,
        glob: str | None = None,
        limit: int = 50,
        regex: bool = False,
    ) -> tuple[list[SearchHit], bool, str | None]:
        """Returns (hits, degraded, reason)."""
        if self._rg:
            hits = self._search_rg(query, glob=glob, limit=limit, regex=regex)
            return hits, False, None
        hits = self._search_re(query, glob=glob, limit=limit, regex=regex)
        return hits, True, "rg not found; used Python re fallback"

    def _search_rg(
        self,
        query: str,
        *,
        glob: str | None,
        limit: int,
        regex: bool,
    ) -> list[SearchHit]:
        assert self._rg is not None
        cmd = [
            self._rg,
            "--line-number",
            "--no-heading",
            "--color",
            "never",
            "--max-count",
            str(limit),
        ]
        if not regex:
            cmd.append("--fixed-strings")
        if glob:
            cmd.extend(["--glob", glob])
        # Never search Neutrino agent caches (even if rg would recurse into them).
        cmd.extend(
            [
                "--glob",
                "!.rna_cache/**",
                "--glob",
                "!.context_cache/**",
            ]
        )
        cmd.extend(["--", query, str(self.root)])
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            return self._search_re(query, glob=glob, limit=limit, regex=regex)
        hits: list[SearchHit] = []
        for line in proc.stdout.splitlines():
            # path:line:snippet
            if ":" not in line:
                continue
            try:
                path_part, rest = line.split(":", 1)
                line_no_s, snippet = rest.split(":", 1)
                line_no = int(line_no_s)
            except ValueError:
                continue
            try:
                rel = str(Path(path_part).resolve().relative_to(self.root)).replace("\\", "/")
            except ValueError:
                rel = path_part
            if self.tree.is_ignored(rel):
                continue
            hits.append(
                SearchHit(
                    file=rel,
                    line=line_no,
                    snippet=snippet.strip(),
                    match=query,
                )
            )
            if len(hits) >= limit:
                break
        return hits

    def _search_re(
        self,
        query: str,
        *,
        glob: str | None,
        limit: int,
        regex: bool,
    ) -> list[SearchHit]:
        import fnmatch

        try:
            pattern = re.compile(query if regex else re.escape(query))
        except re.error:
            pattern = re.compile(re.escape(query))
        hits: list[SearchHit] = []
        for rel in self.tree.list_files():
            if glob and not (fnmatch.fnmatch(rel, glob) or fnmatch.fnmatch(Path(rel).name, glob)):
                continue
            path = self.root / rel
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    hits.append(
                        SearchHit(file=rel, line=i, snippet=line.strip(), match=query)
                    )
                    if len(hits) >= limit:
                        return hits
        return hits
