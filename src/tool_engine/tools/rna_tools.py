"""ToolSpec definitions for rna.* intention tools."""

from __future__ import annotations

from src.config.constants import (
    HLD_DEFAULT_FORMAT,
    HLD_DEFAULT_GRANULARITY,
    LLD_DEFAULT_FORMAT,
    TOOL_AVAILABLE_STATES,
)
from src.tool_engine.models import ToolParam, ToolSpec


def rna_tool_specs() -> list[ToolSpec]:
    return [
        ToolSpec(
            name="rna.find_symbol",
            description="Find symbol definitions in the repository.",
            category="rna",
            handler_key="rna.find_symbol",
            states=TOOL_AVAILABLE_STATES,
            when_to_use="You already know the symbol name and need its definition locus.",
            when_not_to_use="Exploratory 'how does X work' — start with semantic_search or search.",
            pairs_with=("rna.read_file", "rna.find_related", "rna.find_tests"),
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
            states=TOOL_AVAILABLE_STATES,
            when_to_use="You need 'what happens when X runs?' from a known entrypoint.",
            when_not_to_use="You only need a single symbol definition.",
            pairs_with=("rna.find_symbol", "rna.find_related"),
            parameters=(
                ToolParam("entrypoint", "string", True, "Entrypoint symbol or path"),
                ToolParam("max_depth", "integer", False, "Max traversal depth", 4),
                ToolParam(
                    "format",
                    "string",
                    False,
                    "json | mermaid (default json)",
                    "json",
                ),
            ),
        ),
        ToolSpec(
            name="rna.find_tests",
            description="Find tests related to a target symbol or module.",
            category="rna",
            handler_key="rna.find_tests",
            states=TOOL_AVAILABLE_STATES,
            when_to_use="Before modifying behavior, identify existing verification coverage.",
            when_not_to_use="You already know the exact test path — just read or run it.",
            pairs_with=("tests.run", "rna.read_file"),
            parameters=(ToolParam("target", "string", True, "Symbol or module target"),),
        ),
        ToolSpec(
            name="rna.find_related",
            description="Compose callers, tests, and import graph for a symbol.",
            category="rna",
            handler_key="rna.find_related",
            states=TOOL_AVAILABLE_STATES,
            when_to_use="Changing behavior and you need dependents / tests / imports together.",
            when_not_to_use="You only need a definition — use find_symbol.",
            pairs_with=("rna.find_symbol", "rna.find_tests", "rna.read_file"),
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
            states=TOOL_AVAILABLE_STATES,
            when_to_use="Locate concepts or implementations whose exact path/name is unknown.",
            when_not_to_use="You already know the path — use rna.read_file; for exact strings use rna.search.",
            pairs_with=("rna.read_file", "rna.find_symbol"),
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
            states=TOOL_AVAILABLE_STATES,
            when_to_use="You know the path and need contents before editing or answering.",
            when_not_to_use="Never pass absolute paths — use repo-relative paths only; when browsing for unknown locations use search/list first.",
            pairs_with=("executor.apply", "rna.search"),
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
            states=TOOL_AVAILABLE_STATES,
            when_to_use="Exact string, identifier, or error text lookup.",
            when_not_to_use="Concept search without known wording — use semantic_search.",
            pairs_with=("rna.read_file", "rna.list_files"),
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
            states=TOOL_AVAILABLE_STATES,
            when_to_use="Discover paths by name/glob without reading contents.",
            when_not_to_use="Do not use shell ls; do not invent list_dir.",
            pairs_with=("rna.read_file", "rna.search"),
            parameters=(
                ToolParam("pattern", "string", True, "Glob or substring, e.g. '*.py' or 'src/'"),
                ToolParam("limit", "integer", False, "Max paths", 50),
            ),
        ),
        ToolSpec(
            name="rna.get_hld",
            description=(
                "High-level architecture map: package/module dependencies and entrypoints. "
                "Default format=json (token-efficient); use format=mermaid only for human preview."
            ),
            category="rna",
            handler_key="rna.get_hld",
            states=TOOL_AVAILABLE_STATES,
            when_to_use=(
                "Bird's-eye repo or subsystem architecture before large/complex changes; "
                "understand how packages connect."
            ),
            when_not_to_use=(
                "Single-file internals — use rna.get_lld; execution call paths — use rna.trace_workflow."
            ),
            pairs_with=("rna.get_lld", "rna.trace_workflow", "context.resolve"),
            parameters=(
                ToolParam(
                    "scope",
                    "string",
                    False,
                    "Optional repo-relative subtree (e.g. 'src/'); omit for repo-wide",
                ),
                ToolParam(
                    "format",
                    "string",
                    False,
                    "json | mermaid (default json)",
                    HLD_DEFAULT_FORMAT,
                ),
                ToolParam(
                    "granularity",
                    "string",
                    False,
                    "coarse | module | fine | file (default module)",
                    HLD_DEFAULT_GRANULARITY,
                ),
            ),
        ),
        ToolSpec(
            name="rna.get_lld",
            description=(
                "Low-level design for a file or directory: classes, functions, calls, inheritance. "
                "Default format=json; use format=mermaid only for human preview."
            ),
            category="rna",
            handler_key="rna.get_lld",
            states=TOOL_AVAILABLE_STATES,
            when_to_use=(
                "Module/file internals before editing; understand classes and call structure in scope."
            ),
            when_not_to_use=(
                "Repo-wide architecture — use rna.get_hld; cross-file runtime path — use rna.trace_workflow."
            ),
            pairs_with=("rna.get_hld", "rna.read_file", "rna.find_symbol", "rna.trace_workflow"),
            parameters=(
                ToolParam(
                    "scope",
                    "string",
                    True,
                    "Repo-relative file or directory path (required; not whole repo)",
                ),
                ToolParam(
                    "format",
                    "string",
                    False,
                    "json | mermaid (default json)",
                    LLD_DEFAULT_FORMAT,
                ),
            ),
        ),
    ]
