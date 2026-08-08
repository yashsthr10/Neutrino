"""Headless agent CLI — run the Agent Loop on a real repository."""

from __future__ import annotations

import argparse
import sys
import uuid
from pathlib import Path

from src.config.load import load_merged_settings
from src.credentials import build_credential_manager
from src.inference import build_inference
from src.orchestrator import AgentOrchestrator
from src.ports.orchestrator_port import (
    AgentMessage,
    LogLine,
    RunFinished,
    StateTransition,
    ToolCallEvent,
    UIEvent,
)
from src.rna import Rna, RnaConfig
from src.tool_engine import build_tool_engine_from_subsystem


def _print_event(event: UIEvent) -> None:
    if isinstance(event, StateTransition):
        print(f"[state] {event.from_state} -> {event.to_state}", file=sys.stderr)
    elif isinstance(event, ToolCallEvent):
        status = "ok" if event.success else "fail"
        print(f"[tool:{status}] {event.name} {event.args_summary}", file=sys.stderr)
    elif isinstance(event, AgentMessage):
        prefix = "final" if event.final else "agent"
        print(f"[{prefix}] {event.content}")
    elif isinstance(event, LogLine):
        print(f"[log:{event.level}] {event.message}", file=sys.stderr)
    elif isinstance(event, RunFinished):
        print(
            f"[run] {'ok' if event.ok else 'failed'}: {event.message}",
            file=sys.stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m src.agent",
        description="Run the Neutrino Agent Loop against a repository.",
    )
    p.add_argument("task", help="User task / prompt for the agent")
    p.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repository root (default: cwd / settings.repo_path)",
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Auto-approve executor.run shell commands",
    )
    p.add_argument(
        "--fake",
        action="store_true",
        help="Use FakeInferenceProvider (no network; for smoke tests)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    settings = load_merged_settings()
    repo = (args.repo or settings.repo_path).resolve()
    if not repo.is_dir():
        print(f"Not a directory: {repo}", file=sys.stderr)
        return 2

    credentials = build_credential_manager()
    if args.fake:
        from src.inference.providers.fake import FakeInferenceProvider

        inference = build_inference(
            settings,
            credentials,
            fake=FakeInferenceProvider(response_text="No tools needed; task acknowledged."),
            start=True,
        )
    else:
        inference = build_inference(settings, credentials, start=True)

    session_id = uuid.uuid4().hex
    rna = Rna(RnaConfig(repo_path=repo))
    engine = build_tool_engine_from_subsystem(
        rna,
        session_id,
        repo_path=repo,
    )
    orch = AgentOrchestrator(
        _print_event,
        repo,
        inference=inference,
        tool_engine=engine,
        rules=settings.rules,
        auto_approve=bool(args.yes),
        session_id=session_id,
    )
    print(f"Running agent on {repo}", file=sys.stderr)
    orch.run_blocking(args.task)
    status = orch.get_status()
    return 0 if status.get("fsmState") == "DONE" else 1


if __name__ == "__main__":
    raise SystemExit(main())
