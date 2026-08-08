"""RequirementAnalyzer — deterministic ContextRequest -> RetrievalPlan."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath

from src.context.models import ContextRequest


@dataclass(frozen=True, slots=True)
class RetrievalPlan:
    calls: tuple[tuple[str, dict], ...]
    query_conversation: bool = True


class RequirementAnalyzer:
    def analyze(self, request: ContextRequest) -> RetrievalPlan:
        if request.capabilities is not None:
            calls = tuple((name, {}) for name in request.capabilities)
            return RetrievalPlan(calls=calls, query_conversation=True)

        calls: list[tuple[str, dict]] = []
        agent = request.requesting_agent
        complexity = request.task_complexity
        hints = request.file_hints
        symbols = request.symbol_hints

        if agent == "planner":
            calls.extend(self._planner_calls(complexity, hints, symbols))
        elif agent == "coder":
            calls.extend(self._coder_calls(hints, symbols))
        elif agent == "verifier":
            calls.extend(self._verifier_calls(hints))
        elif agent == "reviewer":
            calls.extend(self._reviewer_calls(hints, symbols))

        return RetrievalPlan(calls=tuple(calls), query_conversation=True)

    def _planner_calls(
        self,
        complexity: str,
        hints: tuple[str, ...],
        symbols: tuple[str, ...],
    ) -> list[tuple[str, dict]]:
        calls: list[tuple[str, dict]] = []
        for h in hints:
            calls.append(("get_files_with_name", {"pattern": PurePosixPath(h).name}))
            calls.append(("get_file", {"path": h}))
        if complexity in ("MEDIUM", "COMPLEX"):
            for s in symbols:
                calls.append(("get_symbol", {"name": s, "file_hint": hints[0] if hints else None}))
                calls.append(("get_callers", {"symbol": s, "file_hint": hints[0] if hints else None}))
            if hints:
                scope = str(PurePosixPath(hints[0]).parent)
                if scope == ".":
                    scope = hints[0]
                calls.append(("get_import_graph", {"scope": scope}))
                calls.append(("get_tests", {"target": hints[0]}))
        if complexity == "COMPLEX":
            if hints:
                scope = str(PurePosixPath(hints[0]).parent)
                if scope == ".":
                    scope = hints[0]
                calls.append(("get_hld", {"scope": scope}))
            if symbols:
                calls.append(("get_workflow", {"entrypoint": symbols[0]}))
        return calls

    def _coder_calls(
        self, hints: tuple[str, ...], symbols: tuple[str, ...]
    ) -> list[tuple[str, dict]]:
        calls: list[tuple[str, dict]] = []
        for h in hints:
            calls.append(("get_file", {"path": h}))
        for s in symbols:
            calls.append(("get_symbol", {"name": s, "file_hint": hints[0] if hints else None}))
            calls.append(("get_callers", {"symbol": s, "file_hint": hints[0] if hints else None}))
        return calls

    def _verifier_calls(self, hints: tuple[str, ...]) -> list[tuple[str, dict]]:
        calls: list[tuple[str, dict]] = []
        for h in hints:
            calls.append(("get_tests", {"target": h}))
            calls.append(("get_file", {"path": h}))
        return calls

    def _reviewer_calls(
        self, hints: tuple[str, ...], symbols: tuple[str, ...]
    ) -> list[tuple[str, dict]]:
        calls: list[tuple[str, dict]] = []
        for h in hints:
            calls.append(("get_file", {"path": h}))
        for s in symbols:
            calls.append(("get_callers", {"symbol": s, "file_hint": hints[0] if hints else None}))
        return calls
