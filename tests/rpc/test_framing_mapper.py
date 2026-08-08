"""Tests for NDJSON framing and UIEvent → ui.event mapping."""

from __future__ import annotations

import io
import json

from src.ports.orchestrator_port import (
    AgentMessage,
    ApprovalRequest,
    ContextEdge,
    ContextFileInfo,
    ContextSummary,
    DiffChunk,
    ExplanationAvailable,
    FailureRecovery,
    LogLine,
    PhaseMarker,
    PhaseStepComplete,
    ReasoningBlock,
    RepoTreeSnapshot,
    RunFinished,
    StateTransition,
    StatusSnapshot,
    TaskItem,
    TaskListUpdated,
    ThinkingDelta,
    TokenUpdate,
    ToolCallEvent,
)
from src.rpc.framing import NdjsonWriter, read_messages
from src.rpc.mapper import map_ui_event


def test_ndjson_round_trip() -> None:
    buf = io.StringIO()
    writer = NdjsonWriter(buf)
    writer.write({"jsonrpc": "2.0", "id": 1, "result": {"ok": True}})
    writer.write({"jsonrpc": "2.0", "method": "ui.event", "params": {"type": "log.line"}})
    buf.seek(0)
    messages = list(read_messages(buf))
    assert len(messages) == 2
    assert messages[0]["id"] == 1
    assert messages[1]["method"] == "ui.event"


def test_mapper_covers_all_event_types() -> None:
    cases = [
        (PhaseMarker("PLAN"), "pipeline.progress"),
        (StateTransition("INIT", "PLAN"), "state.changed"),
        (TokenUpdate(10, 100), "tokens.updated"),
        (ToolCallEvent("read", "a.py", True), "tool.called"),
        (LogLine("hi", "info"), "log.line"),
        (AgentMessage("msg", False), "agent.message"),
        (ReasoningBlock("r", True), "reasoning.block"),
        (DiffChunk("a.py", "old", "new"), "diff.updated"),
        (ApprovalRequest("id1", "sum", "prev", None), "approval.requested"),
        (RepoTreeSnapshot("root", ("a", "b")), "repo.tree"),
        (StatusSnapshot("FAST", 1, "PLAN", "SIMPLE"), "status.snapshot"),
        (RunFinished(True, "done"), "execution.finished"),
        (ThinkingDelta("PLAN", "x", True), "activity.delta"),
        (PhaseStepComplete("PLAN", "ok"), "phase.step_complete"),
        (
            ContextSummary(
                (ContextFileInfo("a.py", 1),),
                (ContextEdge("a", "b"),),
                5,
                100,
            ),
            "context.summary",
        ),
        (FailureRecovery("fail", (("r", "Retry"),)), "recovery.requested"),
        (ExplanationAvailable(("b1",)), "explanation.available"),
        (
            TaskListUpdated((TaskItem("1", "do thing", "pending"),)),
            "plan.tasks_updated",
        ),
    ]
    for event, expected_type in cases:
        mapped = map_ui_event(event)
        assert mapped["type"] == expected_type
        assert "payload" in mapped
        # Ensure JSON-serializable
        json.dumps(mapped)
