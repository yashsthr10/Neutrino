"""Serialize capability outputs into LLM-friendly ToolResult payloads."""

from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from typing import Any

from src.config.constants import (
    TOOL_MAX_FILE_CHARS,
    TOOL_MAX_REPO_ITEMS,
    TOOL_MAX_RESULT_BYTES,
    TOOL_MAX_SERIALIZED_MESSAGES,
)
from src.context.models import ContextPackage, ContextResult
from src.rna.models import RnaResult
from src.tool_engine.models import ToolMeta, ToolResult


class ResultSerializer:
    def serialize(
        self,
        raw: Any,
        *,
        cost_ms: float = 0.0,
        tool_version: str = "1",
        success: bool = True,
        errors: tuple[str, ...] = (),
        error_code: str | None = None,
    ) -> ToolResult:
        truncated = False
        degraded = False
        reason: str | None = None

        if isinstance(raw, ToolResult):
            return raw

        if isinstance(raw, ContextResult):
            degraded = raw.meta.degraded
            reason = raw.meta.reason
            data = (
                self._serialize_context_package(raw.data)
                if isinstance(raw.data, ContextPackage)
                else _to_jsonable(raw.data)
            )
            truncated = bool(raw.meta.truncated)
            if isinstance(raw.data, ContextPackage):
                truncated = truncated or raw.data.truncated
        elif isinstance(raw, RnaResult):
            data = raw.to_dict()
            truncated = bool(raw.meta.truncated)
            degraded = bool(raw.meta.degraded)
            reason = raw.meta.reason
            if raw.meta.error and error_code is None:
                error_code = raw.meta.error
        elif isinstance(raw, ContextPackage):
            data = self._serialize_context_package(raw)
            truncated = raw.truncated
        else:
            data = _to_jsonable(raw)

        data, was_capped = _cap_payload(data, TOOL_MAX_RESULT_BYTES)
        truncated = truncated or was_capped
        encoded = json.dumps(data, default=str)
        return ToolResult(
            success=success and error_code not in {"not_implemented", "disabled"},
            data=data,
            meta=ToolMeta(
                cost_ms=cost_ms,
                truncated=truncated,
                degraded=degraded,
                reason=reason,
                error=error_code,
                result_bytes=len(encoded.encode("utf-8")),
                tool_version=tool_version,
            ),
            errors=errors,
        )

    def not_implemented(self, tool_name: str, *, cost_ms: float = 0.0) -> ToolResult:
        return ToolResult(
            success=False,
            data={"tool": tool_name, "status": "not_implemented"},
            meta=ToolMeta(
                cost_ms=cost_ms,
                error="not_implemented",
                reason="Service not wired in Phase A",
                result_bytes=0,
            ),
            errors=("not_implemented",),
        )

    def from_exception(
        self,
        message: str,
        *,
        error_code: str,
        cost_ms: float = 0.0,
    ) -> ToolResult:
        return ToolResult(
            success=False,
            data=None,
            meta=ToolMeta(cost_ms=cost_ms, error=error_code, reason=message),
            errors=(message,),
        )

    def _serialize_context_package(self, package: ContextPackage) -> dict[str, Any]:
        repo_items = []
        for item in package.repository.items[:TOOL_MAX_REPO_ITEMS]:
            payload = _to_jsonable(item.payload)
            if isinstance(payload, dict) and "content" in payload:
                content = str(payload.get("content") or "")
                if len(content) > TOOL_MAX_FILE_CHARS:
                    payload = {
                        **payload,
                        "content": content[:TOOL_MAX_FILE_CHARS],
                        "truncated": True,
                    }
            repo_items.append(
                {
                    "kind": item.kind,
                    "relevance": item.relevance,
                    "tokens_estimate": item.tokens_estimate,
                    "source_method": item.source_method,
                    "payload": payload,
                }
            )
        messages = [
            {"role": m.role, "content": m.content[:500], "id": m.id}
            for m in package.conversation.recent_messages[:TOOL_MAX_SERIALIZED_MESSAGES]
        ]
        return {
            "task_description": package.request.task_description,
            "task_complexity": package.request.task_complexity,
            "requesting_agent": package.request.requesting_agent,
            "tokens_estimate": package.tokens_estimate,
            "token_budget": package.token_budget,
            "truncated": package.truncated,
            "provenance": list(package.provenance),
            "repository": {
                "items": repo_items,
                "item_count": len(package.repository.items),
            },
            "conversation": {
                "recent_messages": messages,
                "summary": (
                    package.conversation.summary.text
                    if package.conversation.summary is not None
                    else None
                ),
            },
        }


def _to_jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, tuple):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _to_jsonable(v) for k, v in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {k: _to_jsonable(v) for k, v in asdict(value).items()}
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return _to_jsonable(value.to_dict())
    return str(value)


def _cap_payload(data: Any, max_bytes: int) -> tuple[Any, bool]:
    encoded = json.dumps(data, default=str)
    if len(encoded.encode("utf-8")) <= max_bytes:
        return data, False
    # Aggressive fallback: keep a short summary
    summary = {
        "truncated": True,
        "note": f"Payload exceeded {max_bytes} bytes",
        "preview": encoded[: max_bytes // 2],
    }
    return summary, True
