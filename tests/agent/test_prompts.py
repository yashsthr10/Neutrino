"""System prompt compiler stays aligned with open AGENT tool surface."""

from __future__ import annotations

from src.agent.prompts import DYNAMIC_BOUNDARY, build_system_prompt, compile_system_prompt
from src.agent.prompts.compiler import PromptInputs
from src.agent.state_model import AgentState
from src.tool_engine.models import ToolParam, ToolSpec
from src.tool_engine.state_policy import AGENT_TOOLS, allowed_tools


def test_agent_prompt_has_layers_and_tools() -> None:
    text = build_system_prompt(
        fsm_state="AGENT",
        user_query="refactor auth architecture and add /health endpoint",
        repo_path="/tmp/repo",
        task_complexity="COMPLEX",
        agent_state=AgentState(phase="IMPLEMENT", objective="Implement"),
    )
    assert "You are Neutrino" in text
    assert DYNAMIC_BOUNDARY in text
    assert "## AVAILABLE CAPABILITIES" in text
    assert "## CURRENT TASK" in text
    assert "refactor auth architecture" in text
    assert "`executor.apply`" in text
    assert "`rna.read_file`" in text
    assert "`rna.get_hld`" in text
    assert "`rna.get_lld`" in text
    assert "Architecture diagrams" in text
    assert "*** Begin Patch" in text
    assert "never invent tool" in text.lower()
    assert "only actor that invokes tools" in text.lower()
    assert "never describe a tool failure as" in text.lower()


def test_legacy_phase_aliases_same_allowlist() -> None:
    assert allowed_tools("PLAN") == AGENT_TOOLS
    assert allowed_tools("EXECUTE") == AGENT_TOOLS
    assert allowed_tools("VERIFY") == AGENT_TOOLS
    assert allowed_tools("AGENT") == AGENT_TOOLS


def test_compile_includes_env_and_agent_state() -> None:
    tools = [
        ToolSpec(
            name="rna.read_file",
            description="Read a file",
            category="rna",
            handler_key="rna.read_file",
            states=frozenset({"AGENT"}),
            when_to_use="When you know the path",
            when_not_to_use="When browsing",
            pairs_with=("rna.search",),
            parameters=(ToolParam("path", "string", True, "path"),),
        )
    ]
    compiled = compile_system_prompt(
        PromptInputs(
            user_query="what is this?",
            repo_path="/repo",
            tools=tools,
            environment={
                "working_directory": "/repo",
                "is_git": True,
                "branch": "main",
                "git_status_summary": "clean",
                "has_tests": True,
            },
            agent_state=AgentState(phase="DISCOVER", objective="Explore"),
            task_complexity="SIMPLE",
        )
    )
    assert "When to use: When you know the path" in compiled.system
    assert "Branch: `main`" in compiled.system
    assert "Phase: DISCOVER" in compiled.system
    assert "**`executor.apply`**" not in compiled.system  # only listed tools in L2


def test_edit_formats_only_when_apply_present() -> None:
    tools = [
        ToolSpec(
            name="rna.list_files",
            description="List",
            category="rna",
            handler_key="rna.list_files",
            states=frozenset({"AGENT"}),
            parameters=(ToolParam("pattern", "string", True, "p"),),
        )
    ]
    compiled = compile_system_prompt(PromptInputs(user_query="list", repo_path="/r", tools=tools))
    assert "*** Begin Patch" not in compiled.system
