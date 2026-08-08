"""C/C++ Tier-3: clangd call hierarchy batch + cscope/ctags fallback."""

from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from src.rna.models import CallEdge, ImportEdge, SymbolRef, WholeProgramGraph

logger = logging.getLogger("rna.cpp_tools")


class CppTier3Provider:
    tier: str = "whole_program"

    def __init__(self, language: str, repo_root: Path, *, timeout_ms: int = 30000) -> None:
        self.language = language
        self.repo_root = repo_root.resolve()
        self.timeout_ms = timeout_ms
        self._clangd = shutil.which("clangd")
        self._cscope = shutil.which("cscope")
        self._ctags = shutil.which("ctags") or shutil.which("universal-ctags")

    def is_available(self) -> bool:
        has_compile_db = (self.repo_root / "compile_commands.json").is_file()
        if self._clangd and has_compile_db:
            return True
        return bool(self._cscope or self._ctags)

    def find_symbol(self, name: str, file_hint: str | None) -> list[SymbolRef]:
        if not self._ctags:
            return []
        try:
            proc = subprocess.run(
                [self._ctags, "-x", "--c-kinds=f", "--c++-kinds=f", "-R", str(self.repo_root)],
                capture_output=True,
                text=True,
                timeout=self.timeout_ms / 1000.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired):
            return []
        out: list[SymbolRef] = []
        short = name.split("::")[-1]
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            sym, kind, line_no = parts[0], parts[1], parts[2]
            if sym != short and sym != name:
                continue
            path = parts[-1] if len(parts) > 3 else ""
            try:
                rel = str(Path(path).resolve().relative_to(self.repo_root)).replace("\\", "/")
            except Exception:  # noqa: BLE001
                rel = path
            if file_hint and rel != file_hint:
                continue
            try:
                ln = int(line_no)
            except ValueError:
                ln = 1
            out.append(
                SymbolRef(
                    name=sym,
                    kind="function" if kind.startswith("f") else "struct",
                    file=rel,
                    line_start=ln,
                    line_end=ln,
                    language=self.language,
                )
            )
        return out

    def find_imports(self, file_path: str) -> list[ImportEdge]:
        return []

    def find_callers(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        if not self._cscope:
            return []
        try:
            proc = subprocess.run(
                [self._cscope, "-d", "-L", "-3", symbol],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_ms / 1000.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.info("cscope failed: %s", exc)
            return []
        edges: list[CallEdge] = []
        for line in proc.stdout.splitlines():
            parts = line.split()
            if len(parts) < 3:
                continue
            path, func, line_no = parts[0], parts[1], parts[2]
            try:
                rel = str(Path(path).resolve().relative_to(self.repo_root)).replace("\\", "/")
            except Exception:  # noqa: BLE001
                rel = path
            try:
                ln = int(line_no)
            except ValueError:
                ln = 1
            caller = SymbolRef(
                name=func,
                kind="function",
                file=rel,
                line_start=ln,
                line_end=ln,
                language=self.language,
            )
            edges.append(CallEdge(caller=caller, callee_name=symbol, call_site_line=ln))
        return edges

    def find_callees(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        return []

    def build_whole_program_graph(self, scope: str) -> WholeProgramGraph | None:
        # Without a full clangd batch walk, expose ctags symbols only
        symbols = self.find_symbol("", None) if False else []  # noqa: SIM223
        # Collect function tags
        if self._ctags:
            try:
                proc = subprocess.run(
                    [self._ctags, "-x", "--c-kinds=f", "--c++-kinds=f", "-R", str(self.repo_root)],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_ms / 1000.0,
                    check=False,
                )
            except (OSError, subprocess.TimeoutExpired):
                return None
            for line in proc.stdout.splitlines()[:5000]:
                parts = line.split()
                if len(parts) < 3:
                    continue
                sym, _kind, line_no = parts[0], parts[1], parts[2]
                path = parts[-1]
                try:
                    rel = str(Path(path).resolve().relative_to(self.repo_root)).replace("\\", "/")
                    ln = int(line_no)
                except Exception:  # noqa: BLE001
                    continue
                if scope not in (".", "") and not rel.startswith(scope.rstrip("/") ):
                    continue
                symbols.append(
                    SymbolRef(
                        name=sym,
                        kind="function",
                        file=rel,
                        line_start=ln,
                        line_end=ln,
                        language=self.language,
                    )
                )
        if not symbols:
            return None
        return WholeProgramGraph(symbols=tuple(symbols))
