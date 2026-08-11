"""get_tests: reverse-import + naming convention + co-change."""

from __future__ import annotations

from pathlib import Path

from src.rna.adapters.registry import LanguageRegistry
from src.rna.git_analyzer.history import GitHistory
from src.rna.graph_engine.import_graph import ImportGraphBuilder
from src.rna.models import TestLink
from src.rna.repo_analyzer.tree import RepoTree


class TestLinker:
    def __init__(
        self,
        repo_path: Path,
        tree: RepoTree,
        import_graph: ImportGraphBuilder,
        git: GitHistory,
        registry: LanguageRegistry,
    ) -> None:
        self.repo_path = repo_path
        self.tree = tree
        self.import_graph = import_graph
        self.git = git
        self.registry = registry

    def get_tests(self, target: str) -> list[TestLink]:
        # target may be file or symbol
        target_file = target
        if not (self.repo_path / target).exists():
            # treat as symbol — find defining file
            lang = self.registry.primary_language()
            for provider in self.registry.resolve(lang):
                try:
                    syms = provider.find_symbol(target, None)
                except Exception:  # noqa: BLE001
                    continue
                if syms:
                    target_file = syms[0].file
                    break

        links: dict[str, TestLink] = {}

        # 1) reverse imports
        graph = self.import_graph.get_import_graph()
        module_keys = self._module_keys(target_file)
        for edge in graph.edges:
            if (
                edge.to in module_keys
                or edge.to == target_file
                or target_file.endswith(edge.to.replace(".", "/") + ".py")
            ):
                if self._looks_like_test(edge.from_file):
                    links[edge.from_file] = TestLink(
                        test_symbol=None,
                        test_file=edge.from_file,
                        target=target,
                        relation="direct_import",
                        confidence=0.9,
                    )

        # 2) naming convention
        stem = Path(target_file).stem
        if stem.startswith("test_"):
            stem = stem[5:]
        if stem.endswith("_test"):
            stem = stem[:-5]
        for f in self.tree.list_files():
            if not self._looks_like_test(f):
                continue
            name = Path(f).name
            if (
                name == f"test_{stem}.py"
                or name == f"{stem}_test.go"
                or name == f"{stem}.test.ts"
                or name == f"{stem}.test.js"
                or name == f"test_{stem}.cpp"
                or name == f"{stem}_test.py"
            ):
                links.setdefault(
                    f,
                    TestLink(
                        test_symbol=None,
                        test_file=f,
                        target=target,
                        relation="naming_convention",
                        confidence=0.7,
                    ),
                )

        # 3) co-change
        if self.git.is_git_repo():
            for path, score in self.git.co_changed_files(target_file):
                if self._looks_like_test(path):
                    links.setdefault(
                        path,
                        TestLink(
                            test_symbol=None,
                            test_file=path,
                            target=target,
                            relation="co_change",
                            confidence=0.3 + 0.4 * score,
                        ),
                    )

        result = list(links.values())
        result.sort(key=lambda t: (-t.confidence, t.test_file))
        return result

    @staticmethod
    def _looks_like_test(path: str) -> bool:
        name = Path(path).name.lower()
        parts = Path(path).parts
        if "test" in parts or "tests" in parts or "__tests__" in parts:
            return True
        return (
            name.startswith("test_")
            or name.endswith("_test.py")
            or name.endswith("_test.go")
            or ".test." in name
            or name.endswith("_test.cpp")
            or name.endswith("_spec.rb")
        )

    @staticmethod
    def _module_keys(path: str) -> set[str]:
        p = Path(path)
        if p.suffix != ".py":
            return {path}
        parts = list(p.with_suffix("").parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        dotted = ".".join(parts)
        return {path, dotted, parts[-1] if parts else path}
