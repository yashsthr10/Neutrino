"""Tool Engine wire models — LLM-facing request/result/spec shapes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from src.context.runtime.execution_context import ExecutionContext

ParamType = Literal["string", "integer", "number", "boolean", "array", "object"]


@dataclass(frozen=True, slots=True)
class ToolParam:
    name: str
    type: ParamType
    required: bool = True
    description: str = ""
    default: Any = None
    item_type: ParamType = "string"  # element type when type == "array"


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    description: str
    parameters: tuple[ToolParam, ...]
    category: str
    handler_key: str
    states: frozenset[str]
    version: str = "1"
    enabled: bool = True
    when_to_use: str = ""
    when_not_to_use: str = ""
    pairs_with: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolRequest:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    execution_context: ExecutionContext | None = None


@dataclass(frozen=True, slots=True)
class ToolMeta:
    cost_ms: float = 0.0
    truncated: bool = False
    degraded: bool = False
    reason: str | None = None
    error: str | None = None
    result_bytes: int = 0
    tool_version: str = "1"


@dataclass(frozen=True, slots=True)
class ToolResult:
    success: bool
    data: Any = None
    meta: ToolMeta = field(default_factory=ToolMeta)
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "meta": asdict(self.meta),
            "errors": list(self.errors),
        }
