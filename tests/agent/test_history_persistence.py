"""Message history must survive across AgentController phase runs."""

from __future__ import annotations

import json
from collections.abc import Iterator

from src.agent.controller import AgentController
from src.agent.policy import AgentPolicy
from src.context.runtime.execution_context import ExecutionContext
from src.context.runtime.request_context import RequestContext
from src.inference.models.capabilities import ProviderCapabilities
from src.inference.models.request import InferenceRequest, ToolCall
from src.inference.models.response import (
    HealthStatus,
    InferenceResponse,
    InferenceStreamEvent,
    ModelInfo,
)
from src.inference.models.usage import Usage
from src.tool_engine import RuntimeServices, build_tool_engine
from src.rna.fake import FakeRna


class ScriptedInference:
    name = "scripted"

    def __init__(self, responses: list[InferenceResponse]) -> None:
        self._responses = list(responses)
        self.chat_calls: list[InferenceRequest] = []

    def connect(self) -> None:
        return None

    def close(self) -> None:
        return None

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True, structured_output=True, streaming=False)

    def health(self) -> HealthStatus:
        return HealthStatus(ok=True, message="ok", models=("scripted",))

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id="scripted")]

    def chat(self, request: InferenceRequest) -> InferenceResponse:
        self.chat_calls.append(request)
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


def test_controller_keeps_tool_history_across_continues(tmp_path) -> None:
    responses = [
        _tools(_tc("rna.list_files", {"pattern": "*.py"}, "1")),
        _final("planned"),
        # continue_phase with same controller
        _final("still remembering"),
    ]
    inference = ScriptedInference(responses)
    engine = build_tool_engine(RuntimeServices(rna=FakeRna(), repo_path=tmp_path))
    controller = AgentController(
        inference=inference,
        tool_engine=engine,
        policy=AgentPolicy(max_iterations=10),
    )
    ctx = ExecutionContext(
        request=RequestContext(
            request_id="r1",
            session_id="s1",
            user_query="inspect then continue",
            repo_path=str(tmp_path),
            requesting_agent="coder",
            task_complexity="SIMPLE",
            created_at="2026-01-01T00:00:00Z",
        )
    )
    r1 = controller.run(context=ctx, fsm_state="AGENT", user_query="inspect then continue")
    assert r1.status == "COMPLETED"
    assert any(m.role == "tool" for m in controller.messages)

    r2 = controller.continue_phase(context=ctx, fsm_state="AGENT")
    assert r2.status == "COMPLETED"

    # Second chat request must still include the earlier tool result.
    assert len(inference.chat_calls) >= 3
    last_msgs = inference.chat_calls[-1].messages
    assert any(getattr(m, "role", None) == "tool" for m in last_msgs)
