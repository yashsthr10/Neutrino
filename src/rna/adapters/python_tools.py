"""Python Tier-3 tools: pyan3 + pyreverse wrappers."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from src.rna.models import CallEdge, ImportEdge, LLDEdge, SymbolRef, WholeProgramGraph

logger = logging.getLogger("rna.python_tools")


class PythonTier3Provider:
    language: str = "python"
    tier: str = "whole_program"

    def __init__(self, repo_root: Path, *, timeout_ms: int = 30000) -> None:
        self.repo_root = repo_root.resolve()
        self.timeout_ms = timeout_ms
        self._pyan = shutil.which("pyan3") or shutil.which("pyan")
        self._pyreverse = shutil.which("pyreverse")

    def is_available(self) -> bool:
        return bool(self._pyan or self._pyreverse)

    def find_symbol(self, name: str, file_hint: str | None) -> list[SymbolRef]:
        return []

    def find_imports(self, file_path: str) -> list[ImportEdge]:
        return []

    def find_callers(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        graph = self.build_whole_program_graph(file_hint or ".")
        if graph is None:
            return []
        short = symbol.split(".")[-1]
        return [
            e
            for e in graph.call_edges
            if e.callee_name == symbol or e.callee_name.endswith("." + short) or e.callee_name == short
        ]

    def find_callees(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        graph = self.build_whole_program_graph(file_hint or ".")
        if graph is None:
            return []
        short = symbol.split(".")[-1]
        return [
            e
            for e in graph.call_edges
            if e.caller.name == symbol or e.caller.name == short or e.caller.name.endswith("." + short)
        ]

    def build_whole_program_graph(self, scope: str) -> WholeProgramGraph | None:
        call_edges: list[CallEdge] = []
        inherit_edges: list[LLDEdge] = []
        symbols: list[SymbolRef] = []

        if self._pyan:
            call_edges.extend(self._run_pyan(scope))
        if self._pyreverse:
            inh, syms = self._run_pyreverse(scope)
            inherit_edges.extend(inh)
            symbols.extend(syms)

        if not call_edges and not inherit_edges and not symbols:
            return None
        return WholeProgramGraph(
            call_edges=tuple(call_edges),
            inherit_edges=tuple(inherit_edges),
            symbols=tuple(symbols),
        )

    def _scope_files(self, scope: str) -> list[str]:
        base = self.repo_root / scope if scope not in (".", "") else self.repo_root
        if base.is_file() and base.suffix == ".py":
            return [str(base.relative_to(self.repo_root)).replace("\\", "/")]
        files: list[str] = []
        root = base if base.is_dir() else self.repo_root
        for p in root.rglob("*.py"):
            if any(
                part
                in {
                    ".git",
                    ".venv",
                    "venv",
                    "__pycache__",
                    ".rna_cache",
                    ".context_cache",
                }
                for part in p.parts
            ):
                continue
            files.append(str(p.relative_to(self.repo_root)).replace("\\", "/"))
        return files

    def _run_pyan(self, scope: str) -> list[CallEdge]:
        assert self._pyan
        files = self._scope_files(scope)
        if not files:
            return []
        abs_files = [str(self.repo_root / f) for f in files[:200]]
        try:
            proc = subprocess.run(
                [self._pyan, "--uses", "--defines", "--colored", *abs_files],
                capture_output=True,
                text=True,
                timeout=self.timeout_ms / 1000.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.info("pyan failed: %s", exc)
            return []
        # Also try --tgf for structured output
        edges = self._parse_pyan_text(proc.stdout + "\n" + proc.stderr)
        if edges:
            return edges
        try:
            proc2 = subprocess.run(
                [self._pyan, "--tgf", *abs_files],
                capture_output=True,
                text=True,
                timeout=self.timeout_ms / 1000.0,
                check=False,
            )
            return self._parse_pyan_tgf(proc2.stdout)
        except (OSError, subprocess.TimeoutExpired):
            return edges

    def _parse_pyan_text(self, text: str) -> list[CallEdge]:
        # Formats vary; look for "A uses B" style lines
        edges: list[CallEdge] = []
        for line in text.splitlines():
            m = re.search(r"([\w\.]+)\s+uses\s+([\w\.]+)", line, re.I)
            if not m:
                m = re.search(r"([\w\.]+)\s+->\s+([\w\.]+)", line)
            if not m:
                continue
            caller_name, callee = m.group(1), m.group(2)
            caller = SymbolRef(
                name=caller_name.split(".")[-1],
                kind="function",
                file="",
                line_start=1,
                line_end=1,
                language="python",
            )
            edges.append(CallEdge(caller=caller, callee_name=callee, call_site_line=1))
        return edges

    def _parse_pyan_tgf(self, text: str) -> list[CallEdge]:
        nodes: dict[str, str] = {}
        edges: list[CallEdge] = []
        section = "nodes"
        for line in text.splitlines():
            line = line.strip()
            if line == "#":
                section = "edges"
                continue
            if not line:
                continue
            parts = line.split()
            if section == "nodes" and len(parts) >= 2:
                nodes[parts[0]] = parts[1]
            elif section == "edges" and len(parts) >= 2:
                a, b = parts[0], parts[1]
                caller_name = nodes.get(a, a)
                callee_name = nodes.get(b, b)
                caller = SymbolRef(
                    name=caller_name.split(".")[-1],
                    kind="function",
                    file="",
                    line_start=1,
                    line_end=1,
                    language="python",
                )
                edges.append(CallEdge(caller=caller, callee_name=callee_name, call_site_line=1))
        return edges

    def _run_pyreverse(self, scope: str) -> tuple[list[LLDEdge], list[SymbolRef]]:
        assert self._pyreverse
        target = str(self.repo_root / scope) if scope not in (".", "") else str(self.repo_root)
        with tempfile.TemporaryDirectory() as tmp:
            try:
                proc = subprocess.run(
                    [self._pyreverse, "-o", "json", "-d", tmp, "-p", "rna", target],
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_ms / 1000.0,
                    check=False,
                    cwd=tmp,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                logger.info("pyreverse failed: %s", exc)
                return [], []
            # pyreverse may emit .dot instead depending on version; try both
            inherit: list[LLDEdge] = []
            symbols: list[SymbolRef] = []
            for path in Path(tmp).glob("*"):
                if path.suffix == ".json":
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    inherit.extend(self._parse_pyreverse_json(data, symbols))
                elif path.suffix == ".dot":
                    inherit.extend(self._parse_dot_inherits(path.read_text(encoding="utf-8", errors="replace")))
            if proc.returncode != 0 and not inherit and not symbols:
                # Fallback: parse classes via AST-less empty
                return [], []
            return inherit, symbols

    def _parse_pyreverse_json(self, data: Any, symbols: list[SymbolRef]) -> list[LLDEdge]:
        edges: list[LLDEdge] = []
        # Best-effort for varying pyreverse JSON shapes
        classes = data if isinstance(data, list) else data.get("classes", []) if isinstance(data, dict) else []
        for cls in classes:
            if not isinstance(cls, dict):
                continue
            name = cls.get("name") or cls.get("title") or ""
            if name:
                symbols.append(
                    SymbolRef(
                        name=name,
                        kind="class",
                        file=cls.get("path", ""),
                        line_start=1,
                        line_end=1,
                        language="python",
                    )
                )
            for parent in cls.get("bases", cls.get("inherits", [])) or []:
                pname = parent if isinstance(parent, str) else parent.get("name", "")
                if name and pname:
                    edges.append(
                        LLDEdge(
                            from_id=f":{name}",
                            to_id=f":{pname}",
                            kind="inherits",
                        )
                    )
        return edges

    def _parse_dot_inherits(self, text: str) -> list[LLDEdge]:
        edges: list[LLDEdge] = []
        for m in re.finditer(r'"?([\w\.]+)"?\s*->\s*"?([\w\.]+)"?', text):
            edges.append(LLDEdge(from_id=f":{m.group(1)}", to_id=f":{m.group(2)}", kind="inherits"))
        return edges
