"""Validate tool existence, enablement, state permission, and arguments."""

from __future__ import annotations

from typing import Any

from src.config.constants import TOOL_MAX_LIST_LEN, TOOL_MAX_STRING_LEN
from src.tool_engine.errors import PermissionDenied, ValidationError
from src.tool_engine.models import ToolParam, ToolRequest, ToolSpec
from src.tool_engine.registry import ToolRegistry
from src.tool_engine.state_policy import is_allowed, normalize_state


class ToolValidator:
    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def validate(self, request: ToolRequest, *, state: str) -> ToolSpec:
        spec = self._registry.require_enabled(request.name)
        norm = normalize_state(state)
        if not is_allowed(spec.name, norm) or norm not in spec.states:
            raise PermissionDenied(f"Tool {spec.name!r} is not available in state {norm!r}")
        self._validate_args(spec, request.arguments or {})
        return spec

    def _validate_args(self, spec: ToolSpec, args: dict[str, Any]) -> None:
        if not isinstance(args, dict):
            raise ValidationError("arguments must be an object")
        known = {p.name: p for p in spec.parameters}
        unknown = set(args) - set(known)
        if unknown:
            raise ValidationError(f"Unexpected arguments: {sorted(unknown)}")
        for p in spec.parameters:
            if p.required and p.name not in args and p.default is None:
                raise ValidationError(f"Missing required argument: {p.name}")
            if p.name not in args:
                continue
            self._check_type(p, args[p.name])

    def _check_type(self, param: ToolParam, value: Any) -> None:
        t = param.type
        if t == "string":
            if not isinstance(value, str):
                raise ValidationError(f"{param.name} must be a string")
            max_len = param.max_length if param.max_length is not None else TOOL_MAX_STRING_LEN
            if len(value) > max_len:
                raise ValidationError(f"{param.name} exceeds max length {max_len}")
        elif t == "integer":
            if not isinstance(value, int) or isinstance(value, bool):
                raise ValidationError(f"{param.name} must be an integer")
        elif t == "number":
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise ValidationError(f"{param.name} must be a number")
        elif t == "boolean":
            if not isinstance(value, bool):
                raise ValidationError(f"{param.name} must be a boolean")
        elif t == "array":
            if not isinstance(value, (list, tuple)):
                raise ValidationError(f"{param.name} must be an array")
            if len(value) > TOOL_MAX_LIST_LEN:
                raise ValidationError(f"{param.name} exceeds max array length {TOOL_MAX_LIST_LEN}")
        elif t == "object":
            if not isinstance(value, dict):
                raise ValidationError(f"{param.name} must be an object")
