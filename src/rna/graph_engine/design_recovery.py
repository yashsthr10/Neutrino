"""get_hld / get_lld / get_workflow."""

from __future__ import annotations

from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

from src.config.constants import HLD_DEFAULT_FORMAT, HLD_DEFAULT_GRANULARITY, LLD_DEFAULT_FORMAT

from src.rna.adapters.base import detect_language
from src.rna.adapters.registry import LanguageRegistry
from src.rna.graph_engine.call_graph import CallGraphService
from src.rna.graph_engine.import_graph import ImportGraphBuilder
from src.rna.graph_engine.symbol_index import SymbolIndex
from src.rna.models import (
    Confidence,
    HLDEdge,
    HLDGranularity,
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

_KNOWN_ROOTS = frozenset({"src", "lib", "pkg", "app", "tests", "test"})


def _escape_mermaid_label(text: str) -> str:
    """Escape characters that break Mermaid node labels."""
    return text.replace('"', "'").replace("\n", " ")


def _format_mermaid_flowchart(
    edges: list[tuple[str, str, int | str]],
    *,
    max_edges: int | None = None,
) -> str:
    """Build a Mermaid flowchart with safe node ids and human-readable labels.

    Raw ids like ``src/agent`` or ``ext:os.path`` break many Mermaid parsers when
    used directly as node identifiers; map them to ``n0``, ``n1``, … with labels.
    """
    trimmed = edges[:max_edges] if max_edges is not None else edges
    node_ids: set[str] = set()
    for src, dst, _ in trimmed:
        node_ids.add(src)
        node_ids.add(dst)

    id_map = {raw: f"n{i}" for i, raw in enumerate(sorted(node_ids))}

    lines = ["graph TD"]
    for raw in sorted(node_ids):
        mid = id_map[raw]
        lines.append(f'  {mid}["{_escape_mermaid_label(raw)}"]')
    for src, dst, weight in trimmed:
        lines.append(f"  {id_map[src]} -->|{weight}| {id_map[dst]}")
    return "\n".join(lines)


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
        format: Literal["json", "mermaid"] = HLD_DEFAULT_FORMAT,
        granularity: HLDGranularity = HLD_DEFAULT_GRANULARITY,
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
            pkg = self._hld_node_id(f, granularity=granularity)
            package_of[f] = pkg
            nodes_set.add(pkg)
            if self._is_entrypoint(f):
                entrypoints.add(pkg)

        for edge in graph.edges:
            src = package_of.get(edge.from_file) or self._hld_node_id(
                edge.from_file, granularity=granularity
            )
            if edge.external:
                dst = f"ext:{edge.to}"
                nodes_set.add(dst)
            else:
                dst = package_of.get(edge.to) or self._hld_node_id(edge.to, granularity=granularity)
                nodes_set.add(dst)
            if src != dst:
                edge_weights[(src, dst)] += 1

        nodes = tuple(
            HLDNode(
                id=n,
                kind=self._hld_node_kind(n, granularity=granularity),
                entrypoint=n in entrypoints,
            )
            for n in sorted(nodes_set)
        )
        edges = tuple(
            HLDEdge(from_id=a, to_id=b, weight=w) for (a, b), w in sorted(edge_weights.items())
        )
        mermaid = None
        if format == "mermaid":
            mermaid = _format_mermaid_flowchart([(e.from_id, e.to_id, e.weight) for e in edges])
        return HLDModel(nodes=nodes, edges=edges, mermaid=mermaid)

    def get_lld(
        self,
        scope: str,
        *,
        format: Literal["json", "mermaid"] = LLD_DEFAULT_FORMAT,
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
                mermaid = _format_mermaid_flowchart(
                    [(ed.from_id, ed.to_id, ed.kind) for ed in edges],
                    max_edges=200,
                )
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
            mermaid = _format_mermaid_flowchart(
                [(ed.from_id, ed.to_id, ed.kind) for ed in edges],
                max_edges=200,
            )
        return (
            LLDModel(scope=scope, nodes=tuple(nodes), edges=tuple(edges), mermaid=mermaid),
            degraded,
            reason,
            conf,
        )

    @staticmethod
    def _hld_node_id(path: str, *, granularity: HLDGranularity = "module") -> str:
        """Map a repo-relative path to an HLD node id for the requested granularity."""
        normalized = path.replace("\\", "/")
        if granularity == "file":
            return normalized

        parts = Path(normalized).parts
        if not parts:
            return "."

        if granularity == "coarse":
            return parts[0]

        if granularity == "module":
            dir_parts = parts[:-1] if len(parts) > 1 and "." in parts[-1] else parts
            if not dir_parts:
                return parts[0]
            if parts[0] in _KNOWN_ROOTS:
                take = min(2, len(dir_parts))
                return "/".join(dir_parts[:take])
            return dir_parts[0]

        # fine: up to three directory segments under known roots, else two.
        dir_parts = parts[:-1] if len(parts) > 1 and "." in parts[-1] else parts
        if parts[0] in _KNOWN_ROOTS:
            take = min(3, len(dir_parts))
            return "/".join(dir_parts[:take]) if take else parts[0]
        take = min(2, len(dir_parts))
        return "/".join(dir_parts[:take]) if take else parts[0]

    @staticmethod
    def _hld_node_kind(
        node_id: str, *, granularity: HLDGranularity = "module"
    ) -> Literal["package", "module", "external_dependency"]:
        if node_id.startswith("ext:"):
            return "external_dependency"
        if granularity == "file":
            return "module"
        if "/" not in node_id.strip("."):
            return "package"
        return "module"

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
