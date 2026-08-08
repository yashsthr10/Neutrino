"""AgentOrchestrator end-to-end with scripted inference."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest

from src.context.fake import FakeContextManager, FakeConversationManager
from src.context.models import ContextPackage, ContextRequest
from src.context.runtime.conversation_context import ConversationContext
from src.context.runtime.repository_context import RepositoryContext, RepositoryContextItem
from src.execution import ExecutionService
from src.inference.models.capabilities import ProviderCapabilities
from src.inference.models.request import InferenceRequest, ToolCall
from src.inference.models.response import (
    HealthStatus,
    InferenceResponse,
    InferenceStreamEvent,
    ModelInfo,
)
from src.inference.models.usage import Usage
from src.orchestrator import AgentOrchestrator
from src.ports.orchestrator_port import (
    AgentMessage,
    RunFinished,
    StateTransition,
    TaskListUpdated,
    UIEvent,
)
from src.rna.fake import FakeRna
from src.tool_engine import RuntimeServices, build_tool_engine
from src.verification import VerificationService
from src.verification.models import RunnerResult


class ScriptedInference:
    name = "scripted"

    def __init__(self, responses: list[InferenceResponse]) -> None:
        self._responses = list(responses)
        self.connected = False

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True, structured_output=True, streaming=False)

    def health(self) -> HealthStatus:
        return HealthStatus(ok=True, message="ok", models=("scripted",))

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="scripted")]

    def chat(self, request: InferenceRequest) -> InferenceResponse:
        _ = request
        if not self._responses:
            return InferenceResponse(content="done", usage=Usage(), finish_reason="stop")
        return self._responses.pop(0)

    def stream(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]:
        resp = self.chat(request)
        yield InferenceStreamEvent(type="done", finish_reason=resp.finish_reason)


def _tc(name: str, arguments: dict, id_: str) -> ToolCall:
    return ToolCall(id=id_, name=name, arguments=json.dumps(arguments))


def _tools(*calls: ToolCall) -> InferenceResponse:
    return InferenceResponse(
        content=None,
        tool_calls=calls,
        usage=Usage(input_tokens=1, output_tokens=1),
        finish_reason="tool_calls",
    )


def _final(text: str) -> InferenceResponse:
    return InferenceResponse(
        content=text, usage=Usage(input_tokens=1, output_tokens=1), finish_reason="stop"
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("def hello():\n    return 1\n", encoding="utf-8")
    return tmp_path


def test_orchestrator_full_workflow(repo: Path) -> None:
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
    responses = [
        # PLAN
        _tools(_tc("context.resolve", {"task_description": "edit hello"}, "1")),
        _final("planned"),
        # EXECUTE
        _tools(_tc("executor.apply", {"format": "search_replace", "patch": patch}, "2")),
        _final("applied"),
        # VERIFY
        _tools(_tc("tests.run", {}, "3")),
        _final("verified"),
    ]
    inference = ScriptedInference(responses)
    rna = FakeRna()
    rna.files["pkg/mod.py"] = "def hello():\n    return 1\n"
    cm = FakeContextManager()
    req = ContextRequest(
        task_description="edit hello",
        task_complexity="SIMPLE",
        requesting_agent="coder",
    )
    cm.default_package = ContextPackage(
        request=req,
        repository=RepositoryContext(
            items=(
                RepositoryContextItem(
                    kind="file",
                    payload={"path": "pkg/mod.py", "content": rna.files["pkg/mod.py"]},
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
    engine = build_tool_engine(
        RuntimeServices(
            context=cm,
            conversation=FakeConversationManager(),
            rna=rna,
            execution=ExecutionService(repo),
            verification=VerificationService(repo, test_command="true", lint_command="true"),
            repo_path=repo,
        )
    )
    events: list[UIEvent] = []
    orch = AgentOrchestrator(
        events.append,
        repo,
        inference=inference,
        tool_engine=engine,
        auto_approve=True,
    )
    orch.run_blocking("edit hello to return 2")

    transitions = [e for e in events if isinstance(e, StateTransition)]
    assert any(t.to_state == "PLAN" for t in transitions)
    assert any(t.to_state == "EXECUTE" for t in transitions)
    assert any(t.to_state == "VERIFY" for t in transitions)
    assert any(t.to_state == "DONE" for t in transitions)
    finished = [e for e in events if isinstance(e, RunFinished)]
    assert finished and finished[-1].ok is True
    assert "return 2" in (repo / "pkg" / "mod.py").read_text(encoding="utf-8")


def test_orchestrator_appends_conversation_memory(repo: Path) -> None:
    """User + phase finals must land in ConversationManagerPort for later resolve."""
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
    responses = [
        _tools(_tc("context.resolve", {"task_description": "edit hello"}, "1")),
        _final("planned"),
        _tools(_tc("executor.apply", {"format": "search_replace", "patch": patch}, "2")),
        _final("applied"),
        _tools(_tc("tests.run", {}, "3")),
        _final("verified"),
    ]
    inference = ScriptedInference(responses)
    rna = FakeRna()
    rna.files["pkg/mod.py"] = "def hello():\n    return 1\n"
    cm = FakeContextManager()
    conversation = FakeConversationManager(session_id="sess-mem")
    engine = build_tool_engine(
        RuntimeServices(
            context=cm,
            conversation=conversation,
            rna=rna,
            execution=ExecutionService(repo),
            verification=VerificationService(repo, test_command="true", lint_command="true"),
            repo_path=repo,
        )
    )
    orch = AgentOrchestrator(
        lambda _e: None,
        repo,
        inference=inference,
        tool_engine=engine,
        auto_approve=True,
        session_id="sess-mem",
    )
    orch.run_blocking("edit hello to return 2")

    assert conversation.call_counts.get("append", 0) >= 4  # user + 3 phase finals
    roles = [m.role for m in conversation.messages]
    assert roles[0] == "user"
    assert conversation.messages[0].content == "edit hello to return 2"
    assert "assistant" in roles
    assert any("planned" in m.content for m in conversation.messages if m.role == "assistant")
    assert any("verified" in m.content for m in conversation.messages if m.role == "assistant")


def test_orchestrator_memory_visible_to_context_resolve(repo: Path, tmp_path: Path) -> None:
    """End-to-end: append via orchestrator, then real ContextManager.resolve sees it."""
    from src.context.config import ContextConfig
    from src.tool_engine import build_tool_engine_from_subsystem

    responses = [
        _tools(
            _tc(
                "context.resolve",
                {"task_description": "remember prior preference"},
                "1",
            )
        ),
        _final("noted prior preference"),
        _tools(
            _tc(
                "executor.apply",
                {
                    "format": "search_replace",
                    "patch": (
                        "pkg/mod.py\n"
                        "<<<<<<< SEARCH\n"
                        "def hello():\n"
                        "    return 1\n"
                        "=======\n"
                        "def hello():\n"
                        "    return 2\n"
                        ">>>>>>> REPLACE\n"
                    ),
                },
                "2",
            )
        ),
        _final("applied"),
        _tools(_tc("tests.run", {}, "3")),
        _final("verified"),
    ]
    inference = ScriptedInference(responses)
    rna = FakeRna()
    rna.files["pkg/mod.py"] = "def hello():\n    return 1\n"
    session_id = "live-mem"
    engine = build_tool_engine_from_subsystem(
        rna,
        session_id,
        config=ContextConfig(cache_dir=tmp_path / "ctx_cache", cache_enabled=False),
        repo_path=repo,
        test_command="true",
        lint_command="true",
    )
    conversation = engine.services.conversation
    assert conversation is not None

    orch = AgentOrchestrator(
        lambda _e: None,
        repo,
        inference=inference,
        tool_engine=engine,
        auto_approve=True,
        session_id=session_id,
    )
    orch.run_blocking("prefer return 2 for hello")

    recent = conversation.get_recent(n=20).data
    assert any(m.role == "user" and "prefer return 2" in m.content for m in recent)
    assert any(m.role == "assistant" for m in recent)

    # Fresh resolve must pull conversation slice (not empty).
    from src.context.models import ContextRequest

    pkg = engine.services.context.resolve(
        ContextRequest(
            task_description="prefer return 2 for hello",
            task_complexity="SIMPLE",
            requesting_agent="planner",
            conversation_query="prefer return 2",
            session_id=session_id,
        )
    ).data
    assert pkg.conversation.recent_messages
    assert any("prefer return 2" in m.content for m in pkg.conversation.recent_messages)


def test_phase_final_message_is_emitted_once(repo: Path) -> None:
    """Each phase final must produce exactly one agent.message — no duplicates."""
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
    responses = [
        _tools(_tc("context.resolve", {"task_description": "edit hello"}, "1")),
        _final("planned"),
        _tools(_tc("executor.apply", {"format": "search_replace", "patch": patch}, "2")),
        _final("applied"),
        _tools(_tc("tests.run", {}, "3")),
        _final("verified"),
    ]
    inference = ScriptedInference(responses)
    rna = FakeRna()
    rna.files["pkg/mod.py"] = "def hello():\n    return 1\n"
    engine = build_tool_engine(
        RuntimeServices(
            context=FakeContextManager(),
            conversation=FakeConversationManager(),
            rna=rna,
            execution=ExecutionService(repo),
            verification=VerificationService(repo, test_command="true", lint_command="true"),
            repo_path=repo,
        )
    )
    events: list[UIEvent] = []
    orch = AgentOrchestrator(
        events.append,
        repo,
        inference=inference,
        tool_engine=engine,
        auto_approve=True,
    )
    orch.run_blocking("edit hello to return 2")

    messages = [e for e in events if isinstance(e, AgentMessage)]
    assert [m.content for m in messages] == ["planned", "applied", "verified"]
    assert all(m.final for m in messages)


def test_plan_set_tasks_updates_planning_context_and_emits_event(repo: Path) -> None:
    responses = [
        _tools(
            _tc(
                "plan.set_tasks",
                {"tasks": [{"content": "Investigate repo", "status": "in_progress"}]},
                "1",
            )
        ),
        _final("planned"),
    ]
    inference = ScriptedInference(responses)
    rna = FakeRna()
    engine = build_tool_engine(
        RuntimeServices(
            context=FakeContextManager(),
            conversation=FakeConversationManager(),
            rna=rna,
            execution=ExecutionService(repo),
            verification=VerificationService(repo, test_command="true", lint_command="true"),
            repo_path=repo,
        )
    )
    events: list[UIEvent] = []
    orch = AgentOrchestrator(
        events.append,
        repo,
        inference=inference,
        tool_engine=engine,
        auto_approve=True,
    )
    orch.run_blocking("do several things")

    updates = [e for e in events if isinstance(e, TaskListUpdated)]
    assert updates
    assert updates[-1].tasks[0].content == "Investigate repo"
    assert updates[-1].tasks[0].status == "in_progress"


class _FlakyVerification:
    """First tests.run fails; every subsequent call succeeds."""

    def __init__(self) -> None:
        self.calls = 0

    def run_tests(self, *, target: str | None = None) -> RunnerResult:
        _ = target
        self.calls += 1
        ok = self.calls > 1
        return RunnerResult(
            success=ok,
            kind="tests",
            command="pytest",
            exit_code=0 if ok else 1,
            stdout="",
            stderr="" if ok else "AssertionError: boom",
            error=None if ok else "AssertionError: boom",
        )

    def run_lint(self, *, paths: list[str] | None = None) -> RunnerResult:
        _ = paths
        return RunnerResult(success=True, kind="lint", command="ruff", exit_code=0, stdout="", stderr="")


def test_static_landing_page_waives_verify_without_tests(tmp_path: Path) -> None:
    """HTML/CSS-only applies should DONE without forcing pytest."""
    patch = (
        "*** Begin Patch\n"
        "*** Add File: index.html\n"
        "+<html><body><h1>Yash</h1></body></html>\n"
        "*** End Patch\n"
    )
    responses = [
        _final("planned"),
        _tools(_tc("executor.apply", {"format": "patch", "patch": patch}, "1")),
        _final("applied"),
        # VERIFY: no tests.run — runtime should waive
        _final("looks good"),
    ]
    inference = ScriptedInference(responses)
    engine = build_tool_engine(
        RuntimeServices(
            context=FakeContextManager(),
            conversation=FakeConversationManager(),
            rna=FakeRna(),
            execution=ExecutionService(tmp_path),
            verification=VerificationService(tmp_path, test_command="false", lint_command="true"),
            repo_path=tmp_path,
        )
    )
    events: list[UIEvent] = []
    orch = AgentOrchestrator(
        events.append,
        tmp_path,
        inference=inference,
        tool_engine=engine,
        auto_approve=True,
    )
    orch.run_blocking("create a simple landing page for Yash")

    transitions = [(t.from_state, t.to_state) for t in events if isinstance(t, StateTransition)]
    assert ("EXECUTE", "VERIFY") in transitions
    assert transitions[-1] == ("VERIFY", "DONE")
    finished = [e for e in events if isinstance(e, RunFinished)]
    assert finished and finished[-1].ok is True
    assert (tmp_path / "index.html").is_file()


def test_verify_failure_regresses_to_execute_then_completes(repo: Path) -> None:
    first_patch = (
        "pkg/mod.py\n"
        "<<<<<<< SEARCH\n"
        "def hello():\n"
        "    return 1\n"
        "=======\n"
        "def hello():\n"
        "    return 2\n"
        ">>>>>>> REPLACE\n"
    )
    second_patch = (
        "pkg/mod.py\n"
        "<<<<<<< SEARCH\n"
        "def hello():\n"
        "    return 2\n"
        "=======\n"
        "def hello():\n"
        "    return 3\n"
        ">>>>>>> REPLACE\n"
    )
    responses = [
        # PLAN
        _tools(_tc("context.resolve", {"task_description": "edit hello"}, "1")),
        _final("planned"),
        # EXECUTE
        _tools(_tc("executor.apply", {"format": "search_replace", "patch": first_patch}, "2")),
        _final("applied"),
        # VERIFY (fails)
        _tools(_tc("tests.run", {}, "3")),
        _final("found a bug"),
        # EXECUTE (regression fix-up)
        _tools(_tc("executor.apply", {"format": "search_replace", "patch": second_patch}, "4")),
        _final("fixed"),
        # VERIFY (passes)
        _tools(_tc("tests.run", {}, "5")),
        _final("verified"),
    ]
    inference = ScriptedInference(responses)
    rna = FakeRna()
    rna.files["pkg/mod.py"] = "def hello():\n    return 1\n"
    engine = build_tool_engine(
        RuntimeServices(
            context=FakeContextManager(),
            conversation=FakeConversationManager(),
            rna=rna,
            execution=ExecutionService(repo),
            verification=_FlakyVerification(),
            repo_path=repo,
        )
    )
    events: list[UIEvent] = []
    orch = AgentOrchestrator(
        events.append,
        repo,
        inference=inference,
        tool_engine=engine,
        auto_approve=True,
    )
    orch.run_blocking("edit hello to return 2, then fix any bugs")

    transitions = [(t.from_state, t.to_state) for t in events if isinstance(t, StateTransition)]
    assert ("VERIFY", "EXECUTE") in transitions
    assert transitions[-1] == ("VERIFY", "DONE")
    finished = [e for e in events if isinstance(e, RunFinished)]
    assert finished and finished[-1].ok is True
    assert "return 3" in (repo / "pkg" / "mod.py").read_text(encoding="utf-8")
