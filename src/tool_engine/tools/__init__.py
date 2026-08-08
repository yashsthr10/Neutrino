"""Collect all ToolSpecs."""

from __future__ import annotations

from src.tool_engine.models import ToolSpec
from src.tool_engine.tools.context_tools import context_tool_specs
from src.tool_engine.tools.execution_tools import execution_tool_specs
from src.tool_engine.tools.git_tools import git_tool_specs
from src.tool_engine.tools.planning_tools import planning_tool_specs
from src.tool_engine.tools.research_tools import research_tool_specs
from src.tool_engine.tools.rna_tools import rna_tool_specs
from src.tool_engine.tools.verification_tools import verification_tool_specs


def all_tool_specs() -> list[ToolSpec]:
    return [
        *context_tool_specs(),
        *rna_tool_specs(),
        *research_tool_specs(),
        *execution_tool_specs(),
        *verification_tool_specs(),
        *git_tool_specs(),
        *planning_tool_specs(),
    ]
