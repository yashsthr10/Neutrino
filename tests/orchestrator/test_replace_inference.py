"""AgentOrchestrator.replace_inference hot-swap."""

from __future__ import annotations

from pathlib import Path

from src.agent.policy import AgentPolicy
from src.context.fake import FakeContextManager, FakeConversationManager
from src.execution import ExecutionService
from src.inference.models.request import InferenceRequest
from src.inference.models.response import HealthStatus, InferenceResponse, ModelInfo
from src.inference.models.usage import Usage
from src.inference.models.capabilities import ProviderCapabilities
from src.orchestrator import AgentOrchestrator
from src.rna.fake import FakeRna
from src.tool_engine import RuntimeServices, build_tool_engine
from src.verification import VerificationService
from collections.abc import Iterator
from src.inference.models.response import InferenceStreamEvent


class _NamedFake:
    name = "named"

    def __init__(self, label: str) -> None:
        self.label = label
        self.closed = False
        self.chat_calls: list[InferenceRequest] = []

    def connect(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(tools=True, structured_output=True, streaming=False)

    def health(self) -> HealthStatus:
        return HealthStatus(ok=True, message=self.label, models=(self.label,))

    def list_models(self) -> list[ModelInfo]:
        return [ModelInfo(id=self.label)]

    def chat(self, request: InferenceRequest) -> InferenceResponse:
        self.chat_calls.append(request)
        return InferenceResponse(
            content=f"from-{self.label}",
            usage=Usage(),
            finish_reason="stop",
            model=self.label,
        )

    def stream(self, request: InferenceRequest) -> Iterator[InferenceStreamEvent]:
        _ = self.chat(request)
        yield InferenceStreamEvent(type="done", finish_reason="stop")


def test_replace_inference_swaps_backend(tmp_path: Path) -> None:
    first = _NamedFake("llama3.2")
    second = _NamedFake("gemini-2.5-flash")
    engine = build_tool_engine(
        RuntimeServices(
            context=FakeContextManager(),
            conversation=FakeConversationManager(),
            rna=FakeRna(),
            execution=ExecutionService(tmp_path),
            verification=VerificationService(tmp_path, test_command="true"),
            repo_path=tmp_path,
        )
    )
    events: list = []
    orch = AgentOrchestrator(
        events.append,
        tmp_path,
        inference=first,
        tool_engine=engine,
        auto_approve=True,
    )
    orch.replace_inference(second)
    assert first.closed is True
    # Drive one phase — should use second backend
    from src.agent.controller import AgentController
    from src.context.runtime.execution_context import ExecutionContext
    from src.context.runtime.request_context import RequestContext
    from datetime import datetime, timezone

    ctrl = AgentController(
        inference=orch._inference,
        tool_engine=engine,
        policy=AgentPolicy(max_iterations=2),
    )
    ctx = ExecutionContext(
        request=RequestContext(
            request_id="1",
            session_id="s",
            user_query="hi",
            repo_path=str(tmp_path),
            requesting_agent="coder",
            task_complexity="SIMPLE",
            created_at=datetime.now(timezone.utc).isoformat(),
        )
    )
    result = ctrl.run(context=ctx, fsm_state="PLAN", user_query="hi")
    assert result.final_text == "from-gemini-2.5-flash"
    assert len(second.chat_calls) >= 1
    assert len(first.chat_calls) == 0
