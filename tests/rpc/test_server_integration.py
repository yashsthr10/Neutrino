"""Integration tests for RpcServer + AgentOrchestrator over in-memory NDJSON."""

from __future__ import annotations

import io
import json
import threading
import time
from pathlib import Path

from src.rpc.framing import NdjsonWriter, read_messages
from tests.rpc.conftest import build_fast_server


class _ThreadSafeBuffer(io.StringIO):
    def __init__(self) -> None:
        super().__init__()
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._closed_write = False

    def write(self, s: str) -> int:  # type: ignore[override]
        with self._cond:
            n = super().write(s)
            self._cond.notify_all()
            return n

    def wait_for_line_count(self, n: int, timeout: float = 5.0) -> None:
        deadline = time.time() + timeout
        with self._cond:
            while self.getvalue().count("\n") < n:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise TimeoutError(f"Expected {n} lines, got {self.getvalue().count(chr(10))}")
                self._cond.wait(timeout=remaining)


def _parse_all(buf: io.StringIO) -> list[dict]:
    buf.seek(0)
    return list(read_messages(buf))


def test_hello_and_execute_streams_events(tmp_path: Path) -> None:
    out = _ThreadSafeBuffer()
    writer = NdjsonWriter(out)
    server = build_fast_server(tmp_path, writer, auto_approve=True)

    hello = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session.hello",
            "params": {"protocolVersion": "1.0.0", "cwd": str(tmp_path)},
        }
    )
    assert hello is not None
    assert hello["result"]["protocolVersion"] == "1.0.0"
    assert hello["result"]["model"] == "test"

    resp = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "runtime.execute",
            "params": {"task": "Implement OAuth"},
        }
    )
    assert resp is not None
    assert resp["result"]["ok"] is True

    deadline = time.time() + 8.0
    finished = False
    while time.time() < deadline:
        messages = _parse_all(out)
        types = [m.get("params", {}).get("type") for m in messages if m.get("method") == "ui.event"]
        if "execution.finished" in types and "state.changed" in types:
            finished = True
            break
        time.sleep(0.05)
    assert finished, f"Did not see finished events: {_parse_all(out)}"


def test_protocol_version_mismatch(tmp_path: Path) -> None:
    out = io.StringIO()
    from src.rpc.server import build_server

    server = build_server(tmp_path, NdjsonWriter(out))
    err = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session.hello",
            "params": {"protocolVersion": "2.0.0", "cwd": str(tmp_path)},
        }
    )
    assert err is not None
    assert "error" in err
    assert err["error"]["code"] == -32000


def test_execute_requires_hello(tmp_path: Path) -> None:
    out = io.StringIO()
    from src.rpc.server import build_server

    server = build_server(tmp_path, NdjsonWriter(out))
    err = server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "runtime.execute",
            "params": {"task": "x"},
        }
    )
    assert err is not None
    assert err["error"]["code"] == -32001


def test_logging_does_not_touch_stdout(tmp_path: Path, capsys) -> None:
    """Writer uses provided stream; sys.stdout must stay clean when using buffer."""
    out = io.StringIO()
    from src.rpc.server import build_server

    server = build_server(tmp_path, NdjsonWriter(out))
    server.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "session.hello",
            "params": {"protocolVersion": "1.0.0", "cwd": str(tmp_path)},
        }
    )
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "protocolVersion" in out.getvalue() or out.getvalue() == ""
    from src.rpc.framing import NdjsonWriter as W

    w = W(out)
    w.write({"jsonrpc": "2.0", "id": 1, "result": {}})
    assert json.loads(out.getvalue().strip().splitlines()[-1])["id"] == 1
