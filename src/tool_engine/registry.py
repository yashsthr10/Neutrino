"""Tool registry — register, lookup, enable/disable, list."""

from __future__ import annotations

from src.tool_engine.errors import ToolDisabled, ToolNotFound
from src.tool_engine.models import ToolSpec
from src.tool_engine.state_policy import is_allowed, normalize_state


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._disabled: set[str] = set()

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec
        if not spec.enabled:
            self._disabled.add(spec.name)

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)
        self._disabled.discard(name)

    def get(self, name: str) -> ToolSpec:
        if name not in self._tools:
            raise ToolNotFound(f"Unknown tool: {name}")
        return self._tools[name]

    def exists(self, name: str) -> bool:
        return name in self._tools

    def enable(self, name: str) -> None:
        self.get(name)  # ensure exists
        self._disabled.discard(name)

    def disable(self, name: str) -> None:
        self.get(name)
        self._disabled.add(name)

    def is_enabled(self, name: str) -> bool:
        return name in self._tools and name not in self._disabled

    def require_enabled(self, name: str) -> ToolSpec:
        spec = self.get(name)
        if name in self._disabled or not spec.enabled:
            raise ToolDisabled(f"Tool disabled: {name}")
        return spec

    def list(
        self,
        *,
        state: str | None = None,
        category: str | None = None,
        include_disabled: bool = False,
    ) -> list[ToolSpec]:
        items = list(self._tools.values())
        if category is not None:
            items = [s for s in items if s.category == category]
        if not include_disabled:
            items = [s for s in items if s.name not in self._disabled and s.enabled]
        if state is not None:
            normalize_state(state)
            items = [s for s in items if is_allowed(s.name, state) and state.upper() in s.states]
        return sorted(items, key=lambda s: s.name)
