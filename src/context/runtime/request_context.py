"""RequestContext — immutable snapshot of the originating user request."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

TaskComplexity = Literal["SIMPLE", "MEDIUM", "COMPLEX"]
RequestingAgent = Literal["planner", "coder", "verifier", "reviewer"]


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str
    session_id: str
    user_query: str
    repo_path: str
    requesting_agent: RequestingAgent
    task_complexity: TaskComplexity
    created_at: str
