"""Tier 1 structural provider via tree-sitter."""

from __future__ import annotations

import re
from pathlib import Path

from tree_sitter import Node, Query, QueryCursor

from src.rna.models import CallEdge, ImportEdge, SymbolRef, WholeProgramGraph

# grammar name for tree_sitter_language_pack
_LANG_GRAMMAR = {
    "python": "python",
    "javascript": "javascript",
    "typescript": "typescript",
    "go": "go",
    "c": "c",
    "cpp": "cpp",
    "rust": "rust",
    "java": "java",
    "ruby": "ruby",
}

_SYMBOL_QUERIES: dict[str, str] = {
    "python": """
        (function_definition name: (identifier) @func)
        (class_definition name: (identifier) @class)
    """,
    "javascript": """
        (function_declaration name: (identifier) @func)
        (class_declaration name: (identifier) @class)
        (method_definition name: (property_identifier) @method)
        (lexical_declaration (variable_declarator name: (identifier) @func value: (arrow_function)))
    """,
    "typescript": """
        (function_declaration name: (identifier) @func)
        (class_declaration name: (type_identifier) @class)
        (method_definition name: (property_identifier) @method)
        (interface_declaration name: (type_identifier) @interface)
    """,
    "go": """
        (function_declaration name: (identifier) @func)
        (method_declaration name: (field_identifier) @method)
        (type_declaration (type_spec name: (type_identifier) @struct type: (struct_type)))
    """,
    "c": """
        (function_definition declarator: (function_declarator declarator: (identifier) @func))
        (struct_specifier name: (type_identifier) @struct)
    """,
    "cpp": """
        (function_definition declarator: (function_declarator declarator: (identifier) @func))
        (class_specifier name: (type_identifier) @class)
        (struct_specifier name: (type_identifier) @struct)
    """,
    "rust": """
        (function_item name: (identifier) @func)
        (struct_item name: (type_identifier) @struct)
        (impl_item type: (type_identifier) @class)
    """,
    "java": """
        (method_declaration name: (identifier) @method)
        (class_declaration name: (identifier) @class)
        (interface_declaration name: (identifier) @interface)
    """,
    "ruby": """
        (method name: (identifier) @method)
        (class name: (constant) @class)
    """,
}

_IMPORT_QUERIES: dict[str, str] = {
    "python": """
        (import_statement name: (dotted_name) @mod)
        (import_from_statement module_name: (dotted_name) @mod)
        (import_from_statement module_name: (relative_import) @mod)
    """,
    "javascript": """
        (import_statement source: (string) @mod)
        (call_expression function: (identifier) @req arguments: (arguments (string) @mod)
          (#eq? @req "require"))
    """,
    "typescript": """
        (import_statement source: (string) @mod)
    """,
    "go": """
        (import_spec path: (interpreted_string_literal) @mod)
    """,
    "c": """
        (preproc_include path: (_) @mod)
    """,
    "cpp": """
        (preproc_include path: (_) @mod)
    """,
    "rust": """
        (use_declaration argument: (scoped_identifier) @mod)
        (use_declaration argument: (identifier) @mod)
    """,
    "java": """
        (import_declaration (scoped_identifier) @mod)
    """,
    "ruby": """
        (call method: (identifier) @req arguments: (argument_list (string) @mod)
          (#match? @req "^(require|require_relative|load)$"))
    """,
}

_CALL_QUERIES: dict[str, str] = {
    "python": """
        (call function: (identifier) @callee)
        (call function: (attribute attribute: (identifier) @callee))
    """,
    "javascript": """
        (call_expression function: (identifier) @callee)
        (call_expression function: (member_expression property: (property_identifier) @callee))
    """,
    "typescript": """
        (call_expression function: (identifier) @callee)
        (call_expression function: (member_expression property: (property_identifier) @callee))
    """,
    "go": """
        (call_expression function: (identifier) @callee)
        (call_expression function: (selector_expression field: (field_identifier) @callee))
    """,
    "c": """
        (call_expression function: (identifier) @callee)
    """,
    "cpp": """
        (call_expression function: (identifier) @callee)
        (call_expression function: (field_expression field: (field_identifier) @callee))
    """,
    "rust": """
        (call_expression function: (identifier) @callee)
        (call_expression function: (field_expression field: (field_identifier) @callee))
    """,
    "java": """
        (method_invocation name: (identifier) @callee)
    """,
    "ruby": """
        (call method: (identifier) @callee)
    """,
}


class TreeSitterProvider:
    language: str
    tier: str = "structural"

    def __init__(self, language: str, repo_root: Path) -> None:
        self.language = language
        self.repo_root = repo_root.resolve()
        self._parser = None
        self._lang = None
        self._available: bool | None = None

    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            from tree_sitter_language_pack import get_language, get_parser

            grammar = _LANG_GRAMMAR.get(self.language)
            if not grammar:
                self._available = False
                return False
            self._lang = get_language(grammar)
            self._parser = get_parser(grammar)
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def _parse(self, source: bytes):
        if not self.is_available() or self._parser is None:
            return None
        return self._parser.parse(source)

    def _read(self, rel_path: str) -> bytes | None:
        path = self.repo_root / rel_path
        if not path.is_file():
            return None
        try:
            return path.read_bytes()
        except OSError:
            return None

    def _query_captures(self, source: bytes, query_src: str) -> dict[str, list[Node]]:
        tree = self._parse(source)
        if tree is None or self._lang is None:
            return {}
        try:
            q = Query(self._lang, query_src)
            cursor = QueryCursor(q)
            return dict(cursor.captures(tree.root_node))
        except Exception:
            return {}

    def _kind_for_capture(self, capture: str) -> str:
        mapping = {
            "func": "function",
            "method": "method",
            "class": "class",
            "interface": "interface",
            "struct": "struct",
        }
        return mapping.get(capture, "function")

    def symbols_in_file(self, rel_path: str) -> list[SymbolRef]:
        source = self._read(rel_path)
        if source is None:
            return []
        qsrc = _SYMBOL_QUERIES.get(self.language)
        if not qsrc:
            return []
        caps = self._query_captures(source, qsrc)
        out: list[SymbolRef] = []
        for capture, nodes in caps.items():
            kind = self._kind_for_capture(capture)
            for node in nodes:
                name = node.text.decode("utf-8", errors="replace") if node.text else ""
                # climb to definition node for line range
                defn = node.parent or node
                out.append(
                    SymbolRef(
                        name=name,
                        kind=kind,  # type: ignore[arg-type]
                        file=rel_path,
                        line_start=defn.start_point[0] + 1,
                        line_end=defn.end_point[0] + 1,
                        signature=None,
                        docstring=None,
                        language=self.language,
                    )
                )
        return out

    def find_symbol(self, name: str, file_hint: str | None) -> list[SymbolRef]:
        short = name.split(".")[-1]
        candidates: list[str] = []
        if file_hint:
            candidates.append(file_hint)
        else:
            # scan all files of this language
            from src.rna.adapters.base import EXT_TO_LANGUAGE

            exts = {ext for ext, lang in EXT_TO_LANGUAGE.items() if lang == self.language}
            for p in self.repo_root.rglob("*"):
                if p.suffix.lower() in exts and p.is_file():
                    try:
                        rel = str(p.relative_to(self.repo_root)).replace("\\", "/")
                    except ValueError:
                        continue
                    if any(
                        part in {".git", "node_modules", ".venv", "venv", "__pycache__"}
                        for part in Path(rel).parts
                    ):
                        continue
                    candidates.append(rel)
        results: list[SymbolRef] = []
        for rel in candidates:
            for sym in self.symbols_in_file(rel):
                if sym.name == short or sym.name == name:
                    results.append(sym)
        # dotted: Class.method — match method inside class file if file_hint given
        if "." in name and not results:
            class_name, method_name = name.rsplit(".", 1)
            for rel in candidates:
                class_syms = [
                    s
                    for s in self.symbols_in_file(rel)
                    if s.name == class_name and s.kind == "class"
                ]
                if not class_syms:
                    continue
                for sym in self.symbols_in_file(rel):
                    if (
                        sym.name == method_name
                        and class_syms[0].line_start <= sym.line_start <= class_syms[0].line_end
                    ):
                        results.append(sym)
        return results

    def find_imports(self, file_path: str) -> list[ImportEdge]:
        source = self._read(file_path)
        if source is None:
            return []
        qsrc = _IMPORT_QUERIES.get(self.language)
        if not qsrc:
            # fallback regex for python
            if self.language == "python":
                return self._python_imports_regex(
                    file_path, source.decode("utf-8", errors="replace")
                )
            return []
        caps = self._query_captures(source, qsrc)
        mods = caps.get("mod", [])
        edges: list[ImportEdge] = []
        for node in mods:
            text = node.text.decode("utf-8", errors="replace") if node.text else ""
            text = text.strip("'\"<>")
            if not text:
                continue
            resolved, external = self._resolve_import(file_path, text)
            edges.append(
                ImportEdge(
                    from_file=file_path,
                    to=resolved,
                    external=external,
                    symbols=(),
                )
            )
        if not edges and self.language == "python":
            return self._python_imports_regex(file_path, source.decode("utf-8", errors="replace"))
        return edges

    def _python_imports_regex(self, file_path: str, text: str) -> list[ImportEdge]:
        edges: list[ImportEdge] = []
        for m in re.finditer(r"^\s*from\s+([\w\.]+)\s+import\s+(.+)$", text, re.M):
            mod = m.group(1)
            syms = tuple(
                s.strip().split(" as ")[0]
                for s in m.group(2).split(",")
                if s.strip() and s.strip() != "("
            )
            resolved, external = self._resolve_import(file_path, mod)
            edges.append(
                ImportEdge(from_file=file_path, to=resolved, external=external, symbols=syms)
            )
        for m in re.finditer(r"^\s*import\s+([\w\.]+(?:\s*,\s*[\w\.]+)*)", text, re.M):
            for part in m.group(1).split(","):
                mod = part.strip().split(" as ")[0].strip()
                if not mod:
                    continue
                resolved, external = self._resolve_import(file_path, mod)
                edges.append(
                    ImportEdge(from_file=file_path, to=resolved, external=external, symbols=())
                )
        return edges

    def _resolve_import(self, from_file: str, module: str) -> tuple[str, bool]:
        if self.language == "python":
            # relative
            if module.startswith("."):
                return module, False
            parts = module.split(".")
            # try package path under repo
            candidates = [
                Path(*parts).with_suffix(".py"),
                Path(*parts) / "__init__.py",
            ]
            # also relative to from_file package
            base = Path(from_file).parent
            for i in range(len(parts)):
                cand = base.joinpath(*parts[: i + 1])
                candidates.append(cand.with_suffix(".py"))
                candidates.append(cand / "__init__.py")
            for cand in candidates:
                full = self.repo_root / cand
                if full.is_file():
                    return str(cand).replace("\\", "/"), False
            return module, True
        if self.language in {"javascript", "typescript"}:
            if module.startswith("."):
                base = (self.repo_root / from_file).parent
                for ext in ("", ".ts", ".tsx", ".js", ".jsx", "/index.ts", "/index.js"):
                    cand = (base / f"{module}{ext}").resolve()
                    try:
                        rel = cand.relative_to(self.repo_root)
                        if cand.is_file():
                            return str(rel).replace("\\", "/"), False
                    except ValueError:
                        continue
                return module, False
            return module, True
        return module, True

    def _enclosing_function(self, source: bytes, line: int) -> SymbolRef | None:
        """Best-effort: find innermost function/method covering `line` (1-indexed)."""
        # Stub — real lookup is filled via find_callers_in_file.
        _ = (source, line)
        return None

    def find_callers(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        short = symbol.split(".")[-1]
        from src.rna.adapters.base import EXT_TO_LANGUAGE

        exts = {ext for ext, lang in EXT_TO_LANGUAGE.items() if lang == self.language}
        files: list[str] = []
        if file_hint:
            files.append(file_hint)
        for p in self.repo_root.rglob("*"):
            if p.suffix.lower() in exts and p.is_file():
                try:
                    rel = str(p.relative_to(self.repo_root)).replace("\\", "/")
                except ValueError:
                    continue
                if any(
                    part in {".git", "node_modules", ".venv", "venv", "__pycache__"}
                    for part in Path(rel).parts
                ):
                    continue
                if rel not in files:
                    files.append(rel)
        edges: list[CallEdge] = []
        qsrc = _CALL_QUERIES.get(self.language, "")
        for rel in files:
            source = self._read(rel)
            if source is None:
                continue
            file_syms = self.symbols_in_file(rel)
            if qsrc:
                caps = self._query_captures(source, qsrc)
                for node in caps.get("callee", []):
                    name = node.text.decode("utf-8", errors="replace") if node.text else ""
                    if name != short:
                        continue
                    line = node.start_point[0] + 1
                    caller = self._symbol_covering(file_syms, line) or SymbolRef(
                        name="<module>",
                        kind="function",
                        file=rel,
                        line_start=line,
                        line_end=line,
                        language=self.language,
                    )
                    edges.append(CallEdge(caller=caller, callee_name=symbol, call_site_line=line))
            else:
                # regex fallback
                text = source.decode("utf-8", errors="replace")
                for i, line_text in enumerate(text.splitlines(), start=1):
                    if re.search(rf"\b{re.escape(short)}\s*\(", line_text):
                        caller = self._symbol_covering(file_syms, i) or SymbolRef(
                            name="<module>",
                            kind="function",
                            file=rel,
                            line_start=i,
                            line_end=i,
                            language=self.language,
                        )
                        edges.append(CallEdge(caller=caller, callee_name=symbol, call_site_line=i))
        return edges

    def find_callees(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        defs = self.find_symbol(symbol, file_hint)
        if not defs:
            return []
        target = defs[0]
        source = self._read(target.file)
        if source is None:
            return []
        qsrc = _CALL_QUERIES.get(self.language, "")
        edges: list[CallEdge] = []
        if qsrc:
            caps = self._query_captures(source, qsrc)
            for node in caps.get("callee", []):
                line = node.start_point[0] + 1
                if target.line_start <= line <= target.line_end:
                    name = node.text.decode("utf-8", errors="replace") if node.text else ""
                    edges.append(CallEdge(caller=target, callee_name=name, call_site_line=line))
        return edges

    def build_whole_program_graph(self, scope: str) -> WholeProgramGraph | None:
        return None

    @staticmethod
    def _symbol_covering(syms: list[SymbolRef], line: int) -> SymbolRef | None:
        covering = [s for s in syms if s.line_start <= line <= s.line_end]
        if not covering:
            return None
        # innermost = smallest span
        covering.sort(key=lambda s: (s.line_end - s.line_start, -s.line_start))
        return covering[0]
