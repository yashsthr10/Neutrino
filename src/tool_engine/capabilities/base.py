"""Capability Layer — runtime service bundle and base types."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.context import ConversationManagerPort, ContextManagerPort
from src.execution import ExecutionPort, GitService
from src.rna import RnaPort
from src.tool_engine.models import ToolResult
from src.tool_engine.serializer import ResultSerializer
from src.verification import VerificationPort


@dataclass
class RuntimeServices:
    """Internal runtime ports. Never exposed directly to the LLM."""

    context: ContextManagerPort | None = None
    conversation: ConversationManagerPort | None = None
    rna: RnaPort | None = None
    execution: ExecutionPort | None = None
    git: GitService | None = None
    verification: VerificationPort | None = None
    repo_path: Path | None = None
    engine: Any | None = None
    inference: Any | None = None
    execution_context: Any | None = None


def stub_result(tool_name: str, serializer: ResultSerializer | None = None) -> ToolResult:
    ser = serializer or ResultSerializer()
    return ser.not_implemented(tool_name)


class CapabilityBase:
    def __init__(
        self, services: RuntimeServices, serializer: ResultSerializer | None = None
    ) -> None:
        self.services = services
        self.serializer = serializer or ResultSerializer()

    def require_context(self) -> ContextManagerPort:
        if self.services.context is None:
            raise RuntimeError("ContextManagerPort is not configured")
        return self.services.context

    def require_conversation(self) -> ConversationManagerPort:
        if self.services.conversation is None:
            raise RuntimeError("ConversationManagerPort is not configured")
        return self.services.conversation

    def session_id(self) -> str | None:
        conv = self.services.conversation
        if conv is None:
            return None
        return getattr(conv, "session_id", None)

    def require_rna(self) -> RnaPort:
        if self.services.rna is None:
            raise RuntimeError("RnaPort is not configured")
        return self.services.rna

    def require_execution(self) -> ExecutionPort:
        if self.services.execution is None:
            raise RuntimeError("ExecutionPort is not configured")
        return self.services.execution

    def require_git(self) -> GitService:
        if self.services.git is None:
            raise RuntimeError("GitService is not configured")
        return self.services.git

    def require_verification(self) -> VerificationPort:
        if self.services.verification is None:
            raise RuntimeError("VerificationPort is not configured")
        return self.services.verification

    def as_handler_map(self) -> dict[str, Any]:
        raise NotImplementedError
