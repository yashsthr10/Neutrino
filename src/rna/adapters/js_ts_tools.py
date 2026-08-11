"""JS/TS Tier-3: madge / dependency-cruiser / ts-morph wrappers."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from pathlib import Path

from src.rna.models import CallEdge, ImportEdge, SymbolRef, WholeProgramGraph

logger = logging.getLogger("rna.js_ts_tools")


class JsTsTier3Provider:
    tier: str = "whole_program"

    def __init__(self, language: str, repo_root: Path, *, timeout_ms: int = 30000) -> None:
        self.language = language
        self.repo_root = repo_root.resolve()
        self.timeout_ms = timeout_ms
        self._madge = shutil.which("madge")
        self._depcruise = shutil.which("dependency-cruiser") or shutil.which("depcruise")

    def is_available(self) -> bool:
        return bool(self._madge or self._depcruise)

    def find_symbol(self, name: str, file_hint: str | None) -> list[SymbolRef]:
        return []

    def find_imports(self, file_path: str) -> list[ImportEdge]:
        graph = self.build_whole_program_graph(".")
        if graph is None:
            return []
        return [e for e in graph.import_edges if e.from_file == file_path]

    def find_callers(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        return []

    def find_callees(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        return []

    def build_whole_program_graph(self, scope: str) -> WholeProgramGraph | None:
        edges: list[ImportEdge] = []
        if self._madge:
            edges.extend(self._run_madge(scope))
        elif self._depcruise:
            edges.extend(self._run_depcruise(scope))
        if not edges:
            return None
        return WholeProgramGraph(import_edges=tuple(edges))

    def _run_madge(self, scope: str) -> list[ImportEdge]:
        assert self._madge
        target = str(self.repo_root / scope) if scope not in (".", "") else str(self.repo_root)
        try:
            proc = subprocess.run(
                [self._madge, "--json", target],
                capture_output=True,
                text=True,
                timeout=self.timeout_ms / 1000.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.info("madge failed: %s", exc)
            return []
        try:
            data = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            return []
        edges: list[ImportEdge] = []
        if isinstance(data, dict):
            for src, deps in data.items():
                for dep in deps or []:
                    edges.append(
                        ImportEdge(
                            from_file=str(src).replace("\\", "/"),
                            to=str(dep).replace("\\", "/"),
                            external=not str(dep).startswith("."),
                        )
                    )
        return edges

    def _run_depcruise(self, scope: str) -> list[ImportEdge]:
        assert self._depcruise
        target = str(self.repo_root / scope) if scope not in (".", "") else str(self.repo_root)
        try:
            proc = subprocess.run(
                [self._depcruise, "--output-type", "json", target],
                capture_output=True,
                text=True,
                timeout=self.timeout_ms / 1000.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.info("dependency-cruiser failed: %s", exc)
            return []
        try:
            data = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            return []
        edges: list[ImportEdge] = []
        modules = data.get("modules", []) if isinstance(data, dict) else []
        for mod in modules:
            src = mod.get("source", "")
            for dep in mod.get("dependencies", []) or []:
                edges.append(
                    ImportEdge(
                        from_file=src,
                        to=dep.get("resolved") or dep.get("module", ""),
                        external=bool(
                            dep.get("dependencyTypes") and "npm" in str(dep.get("dependencyTypes"))
                        ),
                    )
                )
        return edges
