"""ToolSpec definitions for rna.* intention tools."""

from __future__ import annotations

from src.tool_engine.models import ToolParam, ToolSpec

_RNA_STATES = frozenset({"PLAN", "CONTEXT", "EXECUTE"})
_FIND_TESTS_STATES = frozenset({"PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW"})
# Read/list helpers also available during VERIFY for repo-aware checks.
_VERIFY_READ_STATES = frozenset({"PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW"})


def rna_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="rna.find_symbol",
            description="Find symbol definitions in the repository.",
            category="rna",
            handler_key="rna.find_symbol",
            states=_RNA_STATES,
            parameters=(
                ToolParam("name", "string", True, "Symbol name"),
                ToolParam("file_hint", "string", False, "Optional file path hint"),
            ),
        ),
        ToolSpec(
            name="rna.trace_workflow",
            description="Trace a workflow / call path from an entrypoint.",
            category="rna",
            handler_key="rna.trace_workflow",
            states=_RNA_STATES,
            parameters=(
                ToolParam("entrypoint", "string", True, "Entrypoint symbol or path"),
                ToolParam("max_depth", "integer", False, "Max traversal depth", 4),
            ),
        ),
        ToolSpec(
            name="rna.find_tests",
            description="Find tests related to a target symbol or module.",
            category="rna",
            handler_key="rna.find_tests",
            states=_FIND_TESTS_STATES,
            parameters=(ToolParam("target", "string", True, "Symbol or module target"),),
        ),
        ToolSpec(
            name="rna.find_related",
            description="Compose callers, tests, and import graph for a symbol.",
            category="rna",
            handler_key="rna.find_related",
            states=_RNA_STATES,
            parameters=(
                ToolParam("symbol", "string", True, "Symbol name"),
                ToolParam("file_hint", "string", False, "Optional file/module scope"),
                ToolParam("limit", "integer", False, "Caller limit", 25),
            ),
        ),
        ToolSpec(
            name="rna.semantic_search",
            description="Semantic code search over the repository.",
            category="rna",
            handler_key="rna.semantic_search",
            states=_RNA_STATES,
            parameters=(
                ToolParam("query", "string", True, "Natural-language query"),
                ToolParam("limit", "integer", False, "Max hits", 10),
            ),
        ),
        ToolSpec(
            name="rna.read_file",
            description="Read a file or line slice from the repository.",
            category="rna",
            handler_key="rna.read_file",
            states=_VERIFY_READ_STATES,
            parameters=(
                ToolParam("path", "string", True, "Repository-relative file path"),
                ToolParam("start_line", "integer", False, "Optional 1-based start line"),
                ToolParam("end_line", "integer", False, "Optional 1-based end line"),
            ),
        ),
        ToolSpec(
            name="rna.search",
            description="Lexical / literal search across the repository.",
            category="rna",
            handler_key="rna.search",
            states=_RNA_STATES,
            parameters=(
                ToolParam("query", "string", True, "Search query"),
                ToolParam("glob", "string", False, "Optional glob filter"),
                ToolParam("limit", "integer", False, "Max hits", 50),
            ),
        ),
        ToolSpec(
            name="rna.list_files",
            description="List repository files matching a glob/name pattern (use instead of list_dir).",
            category="rna",
            handler_key="rna.list_files",
            states=_VERIFY_READ_STATES,
            parameters=(
                ToolParam("pattern", "string", True, "Glob or substring, e.g. '*.py' or 'src/'"),
                ToolParam("limit", "integer", False, "Max paths", 50),
            ),
        ),
    ]
