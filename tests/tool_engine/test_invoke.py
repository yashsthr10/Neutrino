"""Capability invoke tests against FakeContextManager / FakeRna."""

from __future__ import annotations

from src.context.fake import FakeContextManager
from src.tool_engine import ToolEngine, ToolRequest


def test_context_resolve(engine: ToolEngine, fake_context: FakeContextManager) -> None:
    result = engine.invoke(
        ToolRequest(
            name="context.resolve",
            arguments={"task_description": "Implement OAuth"},
        ),
        state="PLAN",
    )
    assert result.success is True
    assert result.data["task_description"] == "Implement OAuth"
    assert result.data["repository"]["item_count"] == 1
    assert fake_context.call_counts.get("resolve", 0) >= 1


def test_rna_find_symbol(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(name="rna.find_symbol", arguments={"name": "IdentityService"}),
        state="PLAN",
    )
    assert result.success is True
    assert "data" in result.data
    symbols = result.data["data"]
    assert symbols[0]["name"] == "IdentityService"


def test_rna_find_related_composes(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(name="rna.find_related", arguments={"symbol": "IdentityService"}),
        state="PLAN",
    )
    assert result.success is True
    payload = result.data["data"]
    assert payload["symbol"] == "IdentityService"
    assert "callers" in payload
    assert "tests" in payload
    assert "imports" in payload


def test_executor_apply_search_replace(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(
            name="executor.apply",
            arguments={
                "format": "search_replace",
                "patch": (
                    "auth/service.py\n"
                    "<<<<<<< SEARCH\n"
                    "class IdentityService:\n"
                    "    pass\n"
                    "=======\n"
                    "class IdentityService:\n"
                    "    def ok(self):\n"
                    "        return True\n"
                    ">>>>>>> REPLACE\n"
                ),
            },
        ),
        state="EXECUTE",
    )
    assert result.success is True
    assert result.data["change_id"]
    assert result.data["format"] == "search_replace"


def test_executor_run_requires_approval(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(name="executor.run", arguments={"command": "echo hi", "approved": False}),
        state="EXECUTE",
    )
    assert result.success is False
    assert result.meta.error == "permission_denied"


def test_rna_read_file_and_search(engine: ToolEngine) -> None:
    read = engine.invoke(
        ToolRequest(name="rna.read_file", arguments={"path": "auth/service.py"}),
        state="PLAN",
    )
    assert read.success is True
    assert read.data["data"]["path"] == "auth/service.py"

    search = engine.invoke(
        ToolRequest(name="rna.search", arguments={"query": "Identity"}),
        state="PLAN",
    )
    assert search.success is True
    assert search.data["data"]

    listed = engine.invoke(
        ToolRequest(name="rna.list_files", arguments={"pattern": "auth/"}),
        state="PLAN",
    )
    assert listed.success is True
    assert "auth/service.py" in listed.data["data"]


def test_research_docs_stub(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(name="research.docs", arguments={"query": "oauth"}),
        state="PLAN",
    )
    assert result.success is False
    assert result.meta.error == "not_implemented"


def test_plan_set_tasks_normalizes_checklist(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(
            name="plan.set_tasks",
            arguments={
                "tasks": [
                    {"content": "Add endpoint"},
                    {"id": "2", "content": "Write tests", "status": "in_progress"},
                    {"content": "bogus status", "status": "not_a_real_status"},
                ]
            },
        ),
        state="PLAN",
    )
    assert result.success is True
    tasks = result.data["tasks"]
    assert tasks[0] == {"id": "1", "content": "Add endpoint", "status": "pending"}
    assert tasks[1] == {"id": "2", "content": "Write tests", "status": "in_progress"}
    assert tasks[2]["status"] == "pending"


def test_plan_set_tasks_requires_content(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(name="plan.set_tasks", arguments={"tasks": [{"status": "pending"}]}),
        state="EXECUTE",
    )
    assert result.success is False
    assert result.meta.error == "validation_error"


def test_result_to_dict(engine: ToolEngine) -> None:
    result = engine.invoke(
        ToolRequest(name="rna.find_symbol", arguments={"name": "IdentityService"}),
        state="PLAN",
    )
    d = result.to_dict()
    assert d["success"] is True
    assert "meta" in d
