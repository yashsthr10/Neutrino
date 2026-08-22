"""AgentLoop with scripted inference + FakeRna/Context tool engine."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.agent.loop import AgentLoop
from src.agent.policy import AgentPolicy
from tests.doubles import FakeContextManager, FakeConversationManager, QueueInference, ScriptedInference
from src.context.models import ContextPackage, ContextRequest
from src.context.runtime.conversation_context import ConversationContext
from src.context.runtime.execution_context import ExecutionContext
from src.context.runtime.repository_context import RepositoryContext, RepositoryContextItem
from src.context.runtime.request_context import RequestContext
from src.inference.errors import ToolUseFailed
from src.inference.models.request import Message, ToolCall
from src.inference.models.response import InferenceResponse
from src.inference.models.usage import Usage
from tests.doubles.rna import FakeRna
from src.rna.models import SymbolRef
from src.tool_engine import RuntimeServices, build_tool_engine
from src.execution import ExecutionService
from src.verification import VerificationService


def _tc(name: str, arguments: dict, id_: str = "1") -> ToolCall:
    return ToolCall(id=id_, name=name, arguments=json.dumps(arguments))


def _resp_tools(*calls: ToolCall) -> InferenceResponse:
    return InferenceResponse(
        content=None,
        tool_calls=calls,
        usage=Usage(input_tokens=5, output_tokens=5),
        finish_reason="tool_calls",
    )


def _resp_final(text: str) -> InferenceResponse:
    return InferenceResponse(
        content=text,
        usage=Usage(input_tokens=5, output_tokens=5),
        finish_reason="stop",
    )


@pytest.fixture
def exec_repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def engine(exec_repo: Path):
    rna = FakeRna()
    rna.symbols["hello"] = [
        SymbolRef(
            name="hello",
            kind="function",
            file="pkg/mod.py",
            line_start=1,
            line_end=2,
        )
    ]
    rna.files["pkg/mod.py"] = "def hello():\n    return 1\n"
    cm = FakeContextManager()
    req = ContextRequest(
        task_description="update hello",
        task_complexity="SIMPLE",
        requesting_agent="coder",
    )
    cm.default_package = ContextPackage(
        request=req,
        repository=RepositoryContext(
            items=(
                RepositoryContextItem(
                    kind="file",
                    payload={"path": "pkg/mod.py", "content": "def hello():\n    return 1\n"},
                    relevance=1.0,
                    tokens_estimate=10,
                    source_method="get_file",
                ),
            ),
            tokens_estimate=10,
            truncated=False,
        ),
        conversation=ConversationContext(
            recent_messages=(),
            summary=None,
            relevant_history=(),
            decisions=(),
            tokens_estimate=0,
            truncated=False,
        ),
        tokens_estimate=10,
        token_budget=8000,
        truncated=False,
        provenance=("fake",),
        created_at="2026-01-01T00:00:00Z",
        cache_key="fake",
    )
    services = RuntimeServices(
        context=cm,
        conversation=FakeConversationManager(),
        rna=rna,
        execution=ExecutionService(exec_repo),
        verification=VerificationService(exec_repo, test_command="true", lint_command="true"),
        repo_path=exec_repo,
    )
    return build_tool_engine(services)


def _ctx(repo: Path) -> ExecutionContext:
    return ExecutionContext(
        request=RequestContext(
            request_id="r1",
            session_id="s1",
            user_query="change hello to return 2",
            repo_path=str(repo),
            requesting_agent="coder",
            task_complexity="SIMPLE",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )


def test_loop_continuous_agent_write_path(engine, exec_repo: Path) -> None:
    patch = (
        "pkg/mod.py\n"
        "<<<<<<< SEARCH\n"
        "def hello():\n"
        "    return 1\n"
        "=======\n"
        "def hello():\n"
        "    return 2\n"
        ">>>>>>> REPLACE\n"
    )
    inference = ScriptedInference(
        [
            _resp_tools(
                _tc(
                    "context.resolve",
                    {"task_description": "change hello to return 2"},
                    "a",
                )
            ),
            _resp_tools(_tc("executor.apply", {"format": "search_replace", "patch": patch}, "b")),
            _resp_tools(_tc("tests.run", {}, "c")),
            _resp_final("tests green"),
        ]
    )
    loop = AgentLoop(inference=inference, tool_engine=engine, policy=AgentPolicy(max_iterations=10))
    result = loop.run(
        context=_ctx(exec_repo),
        fsm_state="AGENT",
        messages=[Message(role="user", content="change hello to return 2")],
    )
    assert result.status == "COMPLETED"
    assert result.final_text == "tests green"
    assert "return 2" in (exec_repo / "pkg" / "mod.py").read_text(encoding="utf-8")
    # System prompt should be layered compiler output.
    assert inference.chat_calls
    sys_msg = inference.chat_calls[0].messages[0]
    assert sys_msg.role == "system"
    assert "You are Neutrino" in (sys_msg.content or "")
    assert "__SYSTEM_PROMPT_DYNAMIC_BOUNDARY__" in (sys_msg.content or "")


def test_loop_qa_path_without_apply(engine, exec_repo: Path) -> None:
    inference = ScriptedInference(
        [
            _resp_tools(_tc("context.resolve", {"task_description": "what is this"}, "a")),
            _resp_final("A small sample package."),
        ]
    )
    loop = AgentLoop(inference=inference, tool_engine=engine, policy=AgentPolicy(max_iterations=10))
    result = loop.run(
        context=_ctx(exec_repo),
        fsm_state="AGENT",
        messages=[Message(role="user", content="what is this?")],
    )
    assert result.status == "COMPLETED"
    assert "sample" in (result.final_text or "").lower()


def test_loop_recovers_from_tool_use_failed_by_retry(engine, exec_repo: Path) -> None:
    """Truncated Groq failure → corrective retry → successful apply."""
    patch = (
        "*** Begin Patch\n"
        "*** Add File: hello.html\n"
        "+<html><body>hi</body></html>\n"
        "*** End Patch\n"
    )
    truncated = (
        "I'll create a page.\n"
        "<tool_call>\n"
        "<function=executor.apply>\n"
        "<parameter=patch>\n"
        "*** Begin Patch\n"
        "*** Add File: hello.html\n"
        "+<html>\n"
    )
    inference = QueueInference(
        [
            ToolUseFailed("Failed to call a function", failed_generation=truncated),
            _resp_tools(_tc("executor.apply", {"format": "patch", "patch": patch}, "x")),
            _resp_final("created"),
        ]
    )
    loop = AgentLoop(
        inference=inference,
        tool_engine=engine,
        policy=AgentPolicy(max_iterations=10, max_tool_failures=3),
    )
    result = loop.run(
        context=_ctx(exec_repo),
        fsm_state="EXECUTE",
        messages=[Message(role="user", content="make a landing page")],
    )
    assert result.status == "COMPLETED"
    assert (exec_repo / "hello.html").read_text(
        encoding="utf-8"
    ) == "<html><body>hi</body></html>\n"
    assert len(inference.chat_calls) == 3


def test_loop_salvages_complete_xml_tool_call(engine, exec_repo: Path) -> None:
    complete = (
        "<tool_call>\n"
        "<function=executor.apply>\n"
        "<parameter=format>\n"
        "patch\n"
        "</parameter>\n"
        "<parameter=patch>\n"
        "*** Begin Patch\n"
        "*** Add File: page.html\n"
        "+ok\n"
        "*** End Patch\n"
        "</parameter>\n"
        "</function>\n"
        "</tool_call>\n"
    )
    inference = QueueInference(
        [
            ToolUseFailed("tool_use_failed", failed_generation=complete),
            _resp_final("done after salvage"),
        ]
    )
    loop = AgentLoop(
        inference=inference,
        tool_engine=engine,
        policy=AgentPolicy(max_iterations=10),
    )
    result = loop.run(
        context=_ctx(exec_repo),
        fsm_state="EXECUTE",
        messages=[Message(role="user", content="write page")],
    )
    assert result.status == "COMPLETED"
    assert (exec_repo / "page.html").read_text(encoding="utf-8") == "ok\n"
