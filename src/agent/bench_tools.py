"""Offline micro-benchmark for ToolEngine.invoke (no LLM).

Usage:
  python -m src.agent.bench_tools --repo .
  python -m src.agent.bench_tools --repo . --rounds 3
"""

from __future__ import annotations

import argparse
import statistics
import time
import uuid
from pathlib import Path

from src.rna import Rna, RnaConfig
from src.tool_engine import build_tool_engine_from_subsystem
from src.tool_engine.models import ToolRequest


def _bench_one(engine, name: str, arguments: dict, *, state: str = "AGENT") -> float:
    t0 = time.perf_counter()
    result = engine.invoke(ToolRequest(name=name, arguments=arguments), state=state)
    wall_ms = (time.perf_counter() - t0) * 1000.0
    reported = float(result.meta.cost_ms or 0.0)
    return max(wall_ms, reported)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Benchmark ToolEngine tool latency (no LLM).")
    p.add_argument("--repo", type=Path, default=Path("."), help="Repository root")
    p.add_argument("--rounds", type=int, default=3, help="Rounds per tool")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo = args.repo.resolve()
    session_id = uuid.uuid4().hex
    rna = Rna(RnaConfig(repo_path=repo))
    engine = build_tool_engine_from_subsystem(rna, session_id, repo_path=repo)

    suite: list[tuple[str, dict]] = [
        ("verify.probe", {}),
        ("rna.list_files", {"pattern": "*.py", "limit": 20}),
        ("rna.find_tests", {"target": "app"}),
        ("rna.read_file", {"path": "README.md"}),
        ("context.resolve", {"task_description": "benchmark resolve", "task_complexity": "SIMPLE"}),
    ]

    print(f"repo={repo} rounds={args.rounds}")
    print(f"{'tool':<22} {'avg_ms':>10} {'min':>8} {'max':>8} {'n':>4}")
    for name, arguments in suite:
        samples: list[float] = []
        for _ in range(max(1, args.rounds)):
            try:
                samples.append(_bench_one(engine, name, arguments))
            except Exception as exc:  # noqa: BLE001
                print(f"{name:<22} ERROR {exc}")
                samples = []
                break
        if not samples:
            continue
        print(
            f"{name:<22} {statistics.mean(samples):10.1f} "
            f"{min(samples):8.1f} {max(samples):8.1f} {len(samples):4d}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
