"""get_hld / get_lld / get_workflow."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

from src.rna.adapters.base import detect_language
from src.rna.adapters.registry import LanguageRegistry
from src.rna.graph_engine.call_graph import CallGraphService
from src.rna.graph_engine.import_graph import ImportGraphBuilder
from src.rna.graph_engine.symbol_index import SymbolIndex
from src.rna.models import (
    Confidence,
    HLDEdge,
    HLDModel,
    HLDNode,
    LLDEdge,
    LLDModel,
    LLDNode,
    SymbolRef,
    WorkflowStep,
    WorkflowTrace,
)
from src.rna.repo_analyzer.tree import RepoTree


class DesignRecovery:
    def __init__(
        self,
        registry: LanguageRegistry,
        tree: RepoTree,
        import_graph: ImportGraphBuilder,
        call_graph: CallGraphService,
        symbol_index: SymbolIndex,
        *,
        max_depth: int = 6,
    ) -> None:
        self.registry = registry
        self.tree = tree
        self.import_graph = import_graph
        self.call_graph = call_graph
        self.symbol_index = symbol_index
        self.max_depth_hard = max_depth

    def get_workflow(self, entrypoint: str, *, max_depth: int = 4) -> WorkflowTrace:
        depth_cap = min(max_depth, self.max_depth_hard)
        file_hint = None
        symbol = entrypoint
        if ":" in entrypoint and not entrypoint.startswith(":"):
            # file:line or file:symbol
            maybe_file, rest = entrypoint.split(":", 1)
            if (self.registry.repo_root / maybe_file).exists():
                file_hint = maybe_file
                symbol = rest
        syms, _, _ = self.symbol_index.get_symbol(symbol, file_hint=file_hint)
        if not syms:
            return WorkflowTrace(entrypoint=entrypoint, steps=(), truncated_by_depth=False)
        start = syms[0]
        steps: list[WorkflowStep] = [WorkflowStep(symbol=start, depth=0, call_site_line=None)]
        visited: set[str] = {f"{start.file}:{start.name}"}
        queue: deque[tuple[SymbolRef, int]] = deque([(start, 0)])
        truncated = False
        while queue:
            current, depth = queue.popleft()
            if depth >= depth_cap:
                truncated = True
                continue
            callees, _ = self.call_graph.get_callees(current.name, file_hint=current.file)
            for edge in callees:
                # resolve callee symbol
                cdefs, _, _ = self.symbol_index.get_symbol(edge.callee_name, file_hint=None)
                if not cdefs:
                    # still record as synthetic
                    synth = SymbolRef(
                        name=edge.callee_name.split(".")[-1],
                        kind="function",
                        file=current.file,
                        line_start=edge.call_site_line,
                        line_end=edge.call_site_line,
                        language=current.language,
                    )
                    key = f"{synth.file}:{synth.name}:{edge.call_site_line}"
                    if key in visited:
                        continue
                    visited.add(key)
                    steps.append(
                        WorkflowStep(
                            symbol=synth,
                            depth=depth + 1,
                            call_site_line=edge.call_site_line,
                        )
                    )
                    continue
                nxt = cdefs[0]
                key = f"{nxt.file}:{nxt.name}"
                if key in visited:
                    continue
                visited.add(key)
                steps.append(
                    WorkflowStep(
                        symbol=nxt,
                        depth=depth + 1,
                        call_site_line=edge.call_site_line,
                    )
                )
                queue.append((nxt, depth + 1))
        return WorkflowTrace(
            entrypoint=entrypoint,
            steps=tuple(steps),
            truncated_by_depth=truncated,
        )

    def get_hld(
        self,
        *,
        scope: str | None = None,
        format: Literal["json", "mermaid"] = "json",
    ) -> HLDModel:
        graph = self.import_graph.get_import_graph(scope)
        package_of = {}
        nodes_set: set[str] = set()
        edge_weights: dict[tuple[str, str], int] = defaultdict(int)
        entrypoints: set[str] = set()

        files = self.tree.list_files()
        if scope:
            scope_n = scope.rstrip("/")
            files = [f for f in files if f == scope_n or f.startswith(scope_n + "/")]

        for f in files:
            pkg = self._package_id(f)
            package_of[f] = pkg
            nodes_set.add(pkg)
            if self._is_entrypoint(f):
                entrypoints.add(pkg)

        for edge in graph.edges:
            src = package_of.get(edge.from_file) or self._package_id(edge.from_file)
            if edge.external:
                dst = f"ext:{edge.to}"
                nodes_set.add(dst)
            else:
                dst = package_of.get(edge.to) or self._package_id(edge.to)
                nodes_set.add(dst)
            if src != dst:
                edge_weights[(src, dst)] += 1

        nodes = tuple(
            HLDNode(
                id=n,
                kind=(
                    "external_dependency"
                    if n.startswith("ext:")
                    else ("package" if "/" not in n.strip(".") else "module")
                ),
                entrypoint=n in entrypoints,
            )
            for n in sorted(nodes_set)
        )
        edges = tuple(
            HLDEdge(from_id=a, to_id=b, weight=w) for (a, b), w in sorted(edge_weights.items())
        )
        mermaid = None
        if format == "mermaid":
            lines = ["graph TD"]
            for e in edges:
                lines.append(f'  "{e.from_id}" -->|{e.weight}| "{e.to_id}"')
            mermaid = "\n".join(lines)
        return HLDModel(nodes=nodes, edges=edges, mermaid=mermaid)

    def get_lld(
        self,
        scope: str,
        *,
        format: Literal["json", "mermaid"] = "json",
    ) -> tuple[LLDModel, bool, str | None, Confidence]:
        lang = detect_language(scope) or self.registry.primary_language()
        providers = self.registry.resolve(lang)
        degraded = False
        reason: str | None = None
        conf: Confidence = "heuristic"

        # Prefer Tier 3 whole-program
        for provider in providers:
            if provider.tier != "whole_program":
                continue
            try:
                wp = provider.build_whole_program_graph(scope)
            except Exception as exc:  # noqa: BLE001
                reason = f"{provider.__class__.__name__} failed: {exc}"
                continue
            if wp is None:
                reason = reason or "tier3 tool unavailable or returned empty"
                continue
            self.call_graph.remember_whole_program(scope, wp)
            nodes: list[LLDNode] = []
            for sym in wp.symbols:
                if sym.kind in {"class", "function", "method"}:
                    nodes.append(LLDNode(symbol=sym, node_kind=sym.kind))  # type: ignore[arg-type]
            # Also synthesize from call edges
            seen = {n.symbol.name for n in nodes}
            for e in wp.call_edges:
                if e.caller.name not in seen:
                    nodes.append(LLDNode(symbol=e.caller, node_kind="function"))
                    seen.add(e.caller.name)
            edges: list[LLDEdge] = list(wp.inherit_edges)
            for e in wp.call_edges:
                edges.append(
                    LLDEdge(
                        from_id=f"{e.caller.file}:{e.caller.name}",
                        to_id=f":{e.callee_name}",
                        kind="calls",
                    )
                )
            mermaid = None
            if format == "mermaid":
                lines = ["graph TD"]
                for ed in edges[:200]:
                    lines.append(f'  "{ed.from_id}" -->|{ed.kind}| "{ed.to_id}"')
                mermaid = "\n".join(lines)
            return (
                LLDModel(scope=scope, nodes=tuple(nodes), edges=tuple(edges), mermaid=mermaid),
                False,
                None,
                "whole_program",
            )

        # Fallback: Tier 1/2 approximation
        degraded = True
        reason = reason or "no tier3 provider; using structural approximation"
        structural = next((p for p in providers if p.tier == "structural"), None)
        nodes = []
        edges = []
        if structural is not None:
            files = self.tree.list_files()
            scope_n = scope.rstrip("/")
            scoped = [f for f in files if f == scope_n or f.startswith(scope_n + "/") or f == scope]
            if (self.registry.repo_root / scope).is_file():
                scoped = [scope]
            for f in scoped:
                if detect_language(f) != lang:
                    continue
                for sym in structural.symbols_in_file(f):  # type: ignore[attr-defined]
                    if sym.kind in {"class", "function", "method"}:
                        nodes.append(LLDNode(symbol=sym, node_kind=sym.kind))  # type: ignore[arg-type]
                try:
                    for e in structural.find_callees("", f):
                        edges.append(
                            LLDEdge(
                                from_id=f"{e.caller.file}:{e.caller.name}",
                                to_id=f":{e.callee_name}",
                                kind="calls",
                            )
                        )
                except Exception:  # noqa: BLE001
                    pass
                # better: per-symbol callees
                for sym in list(nodes):
                    try:
                        for e in structural.find_callees(sym.symbol.name, f):
                            edges.append(
                                LLDEdge(
                                    from_id=f"{e.caller.file}:{e.caller.name}",
                                    to_id=f":{e.callee_name}",
                                    kind="calls",
                                )
                            )
                    except Exception:  # noqa: BLE001
                        continue
            if any(p.tier == "semantic" for p in providers):
                conf = "precise"
            else:
                conf = "heuristic"
        mermaid = None
        if format == "mermaid":
            lines = ["graph TD"]
            for ed in edges[:200]:
                lines.append(f'  "{ed.from_id}" -->|{ed.kind}| "{ed.to_id}"')
            mermaid = "\n".join(lines)
        return (
            LLDModel(scope=scope, nodes=tuple(nodes), edges=tuple(edges), mermaid=mermaid),
            degraded,
            reason,
            conf,
        )

    @staticmethod
    def _package_id(path: str) -> str:
        parts = Path(path).parts
        if not parts:
            return "."
        if len(parts) == 1:
            return parts[0]
        # first directory as package bucket (src/foo -> src/foo if deeper)
        if parts[0] in {"src", "lib", "pkg", "app", "tests", "test"}:
            if len(parts) >= 2:
                return f"{parts[0]}/{parts[1]}"
            return parts[0]
        return parts[0]

    def _is_entrypoint(self, path: str) -> bool:
        p = self.registry.repo_root / path
        if not p.is_file():
            return False
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        name = Path(path).name
        if name in {
            "main.py",
            "main.go",
            "main.rs",
            "index.js",
            "index.ts",
            "app.py",
            "__main__.py",
        }:
            return True
        if 'if __name__ == "__main__"' in text or "if __name__ == '__main__'" in text:
            return True
        if "func main(" in text:
            return True
        if "@app.route" in text or "@router." in text or "click.command" in text:
            return True
        return False
