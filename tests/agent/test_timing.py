"""TimingStats + model/tool latency wiring in AgentLoop."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.events import ModelCompleted, TimingSummary, ToolCallCompleted
from src.agent.loop import AgentLoop
from src.agent.policy import AgentPolicy
from src.agent.timing import TimingStats
from tests.doubles import FakeContextManager, FakeConversationManager, FakeRna, ScriptedInference
from src.context.runtime.execution_context import ExecutionContext
from src.context.runtime.request_context import RequestContext
from src.inference.models.request import Message, ToolCall
from src.inference.models.response import InferenceResponse
from src.inference.models.usage import Usage
from src.tool_engine import RuntimeServices, build_tool_engine
from src.execution import ExecutionService
from src.verification import VerificationService


def _ctx() -> ExecutionContext:
    return ExecutionContext(
        request=RequestContext(
            request_id="r1",
            session_id="s1",
            user_query="list files",
            repo_path=".",
            requesting_agent="coder",
            task_complexity="SIMPLE",
            created_at="2020-01-01T00:00:00Z",
        )
    )


def test_timing_stats_summary() -> None:
    stats = TimingStats()
    stats.record_model(1000.0, input_tokens=100, output_tokens=20)
    stats.record_model(500.0, input_tokens=50, output_tokens=10)
    stats.record_tool("rna.list_files", 40.0)
    stats.record_tool("rna.list_files", 20.0)
    stats.record_tool("verify.probe", 200.0)
    lines = stats.summary_lines()
    assert any("model 1500ms" in line for line in lines)
    assert any("tools 260ms" in line for line in lines)
    assert stats.to_dict()["model_calls"] == 2
    assert stats.to_dict()["tool_count_by_name"]["rna.list_files"] == 2


def test_loop_records_model_and_tool_timing() -> None:
    events: list[object] = []
    responses = [
        InferenceResponse(
            content=None,
            tool_calls=(
                ToolCall(
                    id="1",
                    name="rna.list_files",
                    arguments=json.dumps({"pattern": "*.py", "limit": 5}),
                ),
            ),
            usage=Usage(input_tokens=10, output_tokens=5),
            finish_reason="tool_calls",
        ),
        InferenceResponse(
            content="listed",
            usage=Usage(input_tokens=12, output_tokens=3),
            finish_reason="stop",
        ),
    ]
    repo = Path(".")
    engine = build_tool_engine(
        RuntimeServices(
            context=FakeContextManager(),
            conversation=FakeConversationManager(),
            rna=FakeRna(),
            execution=ExecutionService(repo),
            verification=VerificationService(repo, test_command="true", lint_command="true"),
            repo_path=repo,
        )
    )
    loop = AgentLoop(
        inference=ScriptedInference(responses),
        tool_engine=engine,
        policy=AgentPolicy(token_budget=1_000_000),
        on_event=events.append,
        auto_approve_shell=True,
    )
    result = loop.run(
        context=_ctx(),
        fsm_state="AGENT",
        messages=[Message(role="user", content="list files")],
    )
    assert result.status == "COMPLETED"
    assert result.timing is not None
    assert result.timing["model_calls"] == 2
    assert result.timing["tool_calls"] >= 1
    assert any(isinstance(e, ModelCompleted) for e in events)
    assert any(isinstance(e, ToolCallCompleted) and e.cost_ms >= 0 for e in events)
    # TimingSummary is orchestrator-owned for COMPLETED; loop still has stats.
    assert not any(isinstance(e, TimingSummary) for e in events)
