"""Go Tier-3: go/callgraph via `go run` helper or gopls batch reuse."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

from src.rna.models import CallEdge, ImportEdge, SymbolRef, WholeProgramGraph

logger = logging.getLogger("rna.go_tools")

_CALLGRAPH_SNIPPET = r"""
package main
import (
  "fmt"
  "golang.org/x/tools/go/callgraph"
  "golang.org/x/tools/go/callgraph/cha"
  "golang.org/x/tools/go/packages"
  "golang.org/x/tools/go/ssa"
  "golang.org/x/tools/go/ssa/ssautil"
)
func main() {
  cfg := &packages.Config{Mode: packages.LoadAllSyntax}
  pkgs, err := packages.Load(cfg, "./...")
  if err != nil { panic(err) }
  prog, _ := ssautil.AllPackages(pkgs, ssa.InstantiateGenerics)
  prog.Build()
  cg := cha.CallGraph(prog)
  _ = callgraph.GraphVisitEdges(cg, func(e *callgraph.Edge) error {
    if e.Caller != nil && e.Callee != None && e.Caller.Func != nil && e.Callee.Func != nil {
      fmt.Printf("%s -> %s\n", e.Caller.Func.String(), e.Callee.Func.String())
    }
    return nil
  })
}
"""


class GoTier3Provider:
    language: str = "go"
    tier: str = "whole_program"

    def __init__(self, repo_root: Path, *, timeout_ms: int = 30000) -> None:
        self.repo_root = repo_root.resolve()
        self.timeout_ms = timeout_ms
        self._go = shutil.which("go")
        self._callgraph_bin = shutil.which("callgraph") or shutil.which("go-callgraph")

    def is_available(self) -> bool:
        return bool(self._go or self._callgraph_bin)

    def find_symbol(self, name: str, file_hint: str | None) -> list[SymbolRef]:
        return []

    def find_imports(self, file_path: str) -> list[ImportEdge]:
        return []

    def find_callers(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        graph = self.build_whole_program_graph(file_hint or ".")
        if graph is None:
            return []
        short = symbol.split(".")[-1]
        return [e for e in graph.call_edges if e.callee_name.endswith(short)]

    def find_callees(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        graph = self.build_whole_program_graph(file_hint or ".")
        if graph is None:
            return []
        short = symbol.split(".")[-1]
        return [e for e in graph.call_edges if e.caller.name.endswith(short)]

    def build_whole_program_graph(self, scope: str) -> WholeProgramGraph | None:
        if self._callgraph_bin:
            return self._run_callgraph_bin()
        # Without a preinstalled helper, degrade — do not download modules during queries
        logger.info("go Tier3: no callgraph binary on PATH; skipping whole-program graph")
        return None

    def _run_callgraph_bin(self) -> WholeProgramGraph | None:
        assert self._callgraph_bin
        try:
            proc = subprocess.run(
                [self._callgraph_bin, "./..."],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=self.timeout_ms / 1000.0,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.info("go callgraph failed: %s", exc)
            return None
        edges: list[CallEdge] = []
        for line in proc.stdout.splitlines():
            m = re.search(r"(.+?)\s*->\s*(.+)", line)
            if not m:
                continue
            caller_name = m.group(1).strip().split("/")[-1]
            callee_name = m.group(2).strip()
            caller = SymbolRef(
                name=caller_name.split(".")[-1],
                kind="function",
                file="",
                line_start=1,
                line_end=1,
                language="go",
            )
            edges.append(CallEdge(caller=caller, callee_name=callee_name, call_site_line=1))
        if not edges:
            return None
        return WholeProgramGraph(call_edges=tuple(edges))
