"""Wall-clock timing for model turns vs tool invokes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field


@dataclass
class TimingStats:
    """Accumulates latency across one agent run (including CONTINUE cycles)."""

    model_calls: int = 0
    model_ms_total: float = 0.0
    model_ms_max: float = 0.0
    tool_calls: int = 0
    tool_ms_total: float = 0.0
    tool_ms_by_name: dict[str, float] = field(default_factory=lambda: defaultdict(float))
    tool_count_by_name: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    input_tokens: int = 0
    output_tokens: int = 0

    def reset(self) -> None:
        self.model_calls = 0
        self.model_ms_total = 0.0
        self.model_ms_max = 0.0
        self.tool_calls = 0
        self.tool_ms_total = 0.0
        self.tool_ms_by_name.clear()
        self.tool_count_by_name.clear()
        self.input_tokens = 0
        self.output_tokens = 0

    def record_model(
        self, latency_ms: float, *, input_tokens: int = 0, output_tokens: int = 0
    ) -> None:
        self.model_calls += 1
        self.model_ms_total += latency_ms
        if latency_ms > self.model_ms_max:
            self.model_ms_max = latency_ms
        self.input_tokens += int(input_tokens)
        self.output_tokens += int(output_tokens)

    def record_tool(self, name: str, cost_ms: float) -> None:
        self.tool_calls += 1
        self.tool_ms_total += cost_ms
        self.tool_ms_by_name[name] += cost_ms
        self.tool_count_by_name[name] += 1

    @property
    def wall_accounted_ms(self) -> float:
        return self.model_ms_total + self.tool_ms_total

    def summary_lines(self, *, top_tools: int = 8) -> list[str]:
        total = self.wall_accounted_ms or 1.0
        model_pct = 100.0 * self.model_ms_total / total
        tool_pct = 100.0 * self.tool_ms_total / total
        avg_model = (
            self.model_ms_total / self.model_calls if self.model_calls else 0.0
        )
        lines = [
            (
                f"timing: model {self.model_ms_total:.0f}ms "
                f"({self.model_calls} calls, avg {avg_model:.0f}ms, "
                f"max {self.model_ms_max:.0f}ms, {model_pct:.0f}%)"
            ),
            (
                f"timing: tools {self.tool_ms_total:.0f}ms "
                f"({self.tool_calls} calls, {tool_pct:.0f}%)"
            ),
            (
                f"timing: tokens in={self.input_tokens} out={self.output_tokens} "
                f"(accounted wall {self.wall_accounted_ms:.0f}ms)"
            ),
        ]
        ranked = sorted(
            self.tool_ms_by_name.items(), key=lambda kv: kv[1], reverse=True
        )[:top_tools]
        if ranked:
            parts = [
                f"{name}={ms:.0f}ms×{self.tool_count_by_name[name]}"
                for name, ms in ranked
            ]
            lines.append("timing: top tools " + ", ".join(parts))
        return lines

    def to_dict(self) -> dict:
        return {
            "model_calls": self.model_calls,
            "model_ms_total": round(self.model_ms_total, 2),
            "model_ms_max": round(self.model_ms_max, 2),
            "tool_calls": self.tool_calls,
            "tool_ms_total": round(self.tool_ms_total, 2),
            "tool_ms_by_name": {
                k: round(v, 2) for k, v in sorted(self.tool_ms_by_name.items())
            },
            "tool_count_by_name": dict(sorted(self.tool_count_by_name.items())),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "wall_accounted_ms": round(self.wall_accounted_ms, 2),
        }
