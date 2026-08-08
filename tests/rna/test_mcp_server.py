"""MCP server round-trip contract tests."""

from __future__ import annotations

import json

from src.rna import Rna
from src.rna.config import RnaConfig
from src.rna.mcp.server import RnaMcpServer


def test_tools_list_and_call_get_hld(python_repo) -> None:
    cfg = RnaConfig(
        repo_path=python_repo,
        cache_dir=python_repo / ".rna_cache",
        enabled_tiers=("structural",),
    )
    rna = Rna(cfg)
    server = RnaMcpServer(rna)

    listed = server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert listed is not None
    tool_names = {t["name"] for t in listed["result"]["tools"]}
    assert "rna_get_hld" in tool_names

    direct = rna.get_hld().to_dict()
    called = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "rna_get_hld", "arguments": {}},
        }
    )
    assert called is not None
    assert called["result"]["isError"] is False
    structured = called["result"]["structuredContent"]
    # Same node/edge counts as direct call
    assert len(structured["data"]["nodes"]) == len(direct["data"]["nodes"])
    assert len(structured["data"]["edges"]) == len(direct["data"]["edges"])
    # text payload is valid JSON of the same result
    text_payload = json.loads(called["result"]["content"][0]["text"])
    assert text_payload["data"]["nodes"] == structured["data"]["nodes"]
