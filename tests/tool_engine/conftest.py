"""Shared fixtures for tool_engine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.doubles.context import FakeContextManager, FakeConversationManager
from src.context.models import ContextPackage, ContextRequest
from src.context.runtime.conversation_context import ConversationContext
from src.context.runtime.repository_context import RepositoryContext, RepositoryContextItem
from src.execution import ExecutionService
from tests.doubles.rna import FakeRna
from src.rna.models import SearchHit, SymbolRef
from src.tool_engine import RuntimeServices, build_tool_engine
from src.verification import VerificationService


@pytest.fixture
def fake_rna() -> FakeRna:
    rna = FakeRna()
    rna.symbols["IdentityService"] = [
        SymbolRef(
            name="IdentityService",
            kind="class",
            file="auth/service.py",
            line_start=1,
            line_end=10,
            signature="class IdentityService",
            docstring=None,
            language="python",
        )
    ]
    rna.files["auth/service.py"] = "class IdentityService:\n    pass\n"
    rna.file_names = ["auth/service.py"]
    rna.search_hits = [
        SearchHit(
            file="auth/service.py",
            line=1,
            snippet="class IdentityService",
            match="IdentityService",
        )
    ]
    return rna


@pytest.fixture
def fake_context() -> FakeContextManager:
    cm = FakeContextManager()
    req = ContextRequest(
        task_description="Implement OAuth",
        task_complexity="MEDIUM",
        requesting_agent="planner",
    )
    pkg = ContextPackage(
        request=req,
        repository=RepositoryContext(
            items=(
                RepositoryContextItem(
                    kind="file",
                    payload={
                        "path": "auth/service.py",
                        "content": "class AuthService:\n    pass\n",
                    },
                    relevance=0.9,
                    tokens_estimate=20,
                    source_method="get_file",
                ),
            ),
            tokens_estimate=20,
            truncated=False,
        ),
        conversation=ConversationContext(
            recent_messages=(),
            summary=None,
            relevant_history=(),
            decisions=(),
            tokens_estimate=0,
            truncated=False,
        ),
        tokens_estimate=20,
        token_budget=8000,
        truncated=False,
        provenance=("fake",),
        created_at="2026-01-01T00:00:00Z",
        cache_key="fake",
    )
    cm.default_package = pkg
    cm.packages["Implement OAuth"] = pkg
    return cm


@pytest.fixture
def exec_repo(tmp_path: Path) -> Path:
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "service.py").write_text(
        "class IdentityService:\n    pass\n", encoding="utf-8"
    )
    return tmp_path


@pytest.fixture
def engine(fake_rna: FakeRna, fake_context: FakeContextManager, exec_repo: Path):
    services = RuntimeServices(
        context=fake_context,
        conversation=FakeConversationManager(),
        rna=fake_rna,
        execution=ExecutionService(exec_repo),
        verification=VerificationService(exec_repo, test_command="true", lint_command="true"),
        repo_path=exec_repo,
    )
    return build_tool_engine(services)
