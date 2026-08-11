"""Map OrchestratorPort UIEvent dataclasses to presentation ui.event payloads."""

from __future__ import annotations

from typing import Any

from src.ports.orchestrator_port import (
    AgentMessage,
    ApprovalRequest,
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
    TaskListUpdated,
    ThinkingDelta,
    TokenUpdate,
    ToolCallEvent,
    UIEvent,
)

_PIPELINE_PHASES = ("PLAN", "CONTEXT", "EXECUTE", "VERIFY", "REVIEW")


def map_ui_event(event: UIEvent) -> dict[str, Any]:
    """Return `{type, payload}` for a `ui.event` notification."""
    if isinstance(event, PhaseMarker):
        phase = event.phase.upper()
        status = "running"
        step = None
        total = len(_PIPELINE_PHASES)
        if phase in _PIPELINE_PHASES:
            step = _PIPELINE_PHASES.index(phase) + 1
        return {
            "type": "pipeline.progress",
            "payload": {
                "phase": phase,
                "status": status,
                "step": step,
                "total": total,
            },
        }
    if isinstance(event, StateTransition):
        return {
            "type": "state.changed",
            "payload": {"from": event.from_state, "to": event.to_state},
        }
    if isinstance(event, TokenUpdate):
        return {
            "type": "tokens.updated",
            "payload": {"used": event.used, "budget": event.budget},
        }
    if isinstance(event, ToolCallEvent):
        return {
            "type": "tool.called",
            "payload": {
                "name": event.name,
                "argsSummary": event.args_summary,
                "success": event.success,
            },
        }
    if isinstance(event, LogLine):
        return {
            "type": "log.line",
            "payload": {"message": event.message, "level": event.level},
        }
    if isinstance(event, AgentMessage):
        return {
            "type": "agent.message",
            "payload": {"content": event.content, "final": event.final},
        }
    if isinstance(event, ReasoningBlock):
        return {
            "type": "reasoning.block",
            "payload": {
                "content": event.content,
                "collapsedDefault": event.collapsed_default,
            },
        }
    if isinstance(event, DiffChunk):
        return {
            "type": "diff.updated",
            "payload": {
                "path": event.path,
                "oldText": event.old_text,
                "newText": event.new_text,
            },
        }
    if isinstance(event, ApprovalRequest):
        return {
            "type": "approval.requested",
            "payload": {
                "requestId": event.request_id,
                "summary": event.summary,
                "previewSnippet": event.preview_snippet,
                "fullFileText": event.full_file_text,
            },
        }
    if isinstance(event, RepoTreeSnapshot):
        return {
            "type": "repo.tree",
            "payload": {
                "rootLabel": event.root_label,
                "paths": list(event.paths),
            },
        }
    if isinstance(event, StatusSnapshot):
        return {
            "type": "status.snapshot",
            "payload": {
                "modeLabel": event.mode_label,
                "tokensUsed": event.tokens_used,
                "fsmState": event.fsm_state,
                "taskComplexity": event.task_complexity,
            },
        }
    if isinstance(event, RunFinished):
        return {
            "type": "execution.finished",
            "payload": {"ok": event.ok, "message": event.message},
        }
    if isinstance(event, ThinkingDelta):
        return {
            "type": "activity.delta",
            "payload": {
                "phaseId": event.phase_id,
                "text": event.text,
                "newline": event.append_newline,
            },
        }
    if isinstance(event, PhaseStepComplete):
        return {
            "type": "phase.step_complete",
            "payload": {"phaseId": event.phase_id, "message": event.message},
        }
    if isinstance(event, ContextSummary):
        return {
            "type": "context.summary",
            "payload": {
                "files": [{"path": f.path, "lineCount": f.line_count} for f in event.files],
                "edges": [{"fromPath": e.from_path, "toPath": e.to_path} for e in event.edges],
                "tokensUsed": event.tokens_used,
                "tokenBudget": event.token_budget,
            },
        }
    if isinstance(event, FailureRecovery):
        return {
            "type": "recovery.requested",
            "payload": {
                "message": event.message,
                "options": [{"id": oid, "label": label} for oid, label in event.options],
            },
        }
    if isinstance(event, ExplanationAvailable):
        return {
            "type": "explanation.available",
            "payload": {"bullets": list(event.bullets)},
        }
    if isinstance(event, TaskListUpdated):
        return {
            "type": "plan.tasks_updated",
            "payload": {
                "tasks": [
                    {"id": t.id, "content": t.content, "status": t.status} for t in event.tasks
                ]
            },
        }
    raise TypeError(f"Unsupported UIEvent type: {type(event)!r}")
