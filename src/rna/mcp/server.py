"""MCP server exposing every rna.* method (stdio JSON-RPC subset + optional TCP)."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, TextIO

from src.rna.config import RnaConfig
from src.rna.facade import Rna
from src.rna.mcp.schema import all_tool_schemas, dispatch


class RnaMcpServer:
    """
    Minimal MCP-compatible tools server.
    Speaks newline-delimited JSON-RPC over stdio (and a simple TCP variant).
    Compatible with MCP clients that call tools/list and tools/call.
    """

    def __init__(self, rna: Rna) -> None:
        self.rna = rna

    def handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        method = message.get("method")
        msg_id = message.get("id")
        params = message.get("params") or {}

        if method == "initialize":
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "rna", "version": "0.1.0"},
                },
            }
        if method == "notifications/initialized":
            return None
        if method == "tools/list":
            tools = []
            for schema in all_tool_schemas():
                tools.append(
                    {
                        "name": schema["name"],
                        "description": schema["description"],
                        "inputSchema": schema["parameters"],
                    }
                )
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}
        if method == "tools/call":
            name = params.get("name", "")
            arguments = params.get("arguments") or {}
            try:
                result = dispatch(self.rna, name, arguments)
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, default=str)}],
                        "isError": False,
                        "structuredContent": result,
                    },
                }
            except Exception as exc:  # noqa: BLE001
                return {
                    "jsonrpc": "2.0",
                    "id": msg_id,
                    "result": {
                        "content": [{"type": "text", "text": str(exc)}],
                        "isError": True,
                    },
                }
        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        # ignore unknown notifications
        if msg_id is None:
            return None
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def serve_stdio(self, stdin: TextIO = sys.stdin, stdout: TextIO = sys.stdout) -> None:
        for line in stdin:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response) + "\n")
                stdout.flush()


def build_server(repo: Path | str, **config_kwargs: Any) -> RnaMcpServer:
    cfg = RnaConfig(repo_path=Path(repo), **config_kwargs)
    return RnaMcpServer(Rna(cfg))
