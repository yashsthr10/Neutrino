"""Generic LSP client (Tier 2) over stdio JSON-RPC."""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from pathlib import Path
from typing import Any

from src.rna.models import CallEdge, ImportEdge, SymbolRef, WholeProgramGraph

logger = logging.getLogger("rna.lsp")


class LspProvider:
    language: str
    tier: str = "semantic"

    def __init__(
        self,
        language: str,
        repo_root: Path,
        binary: str,
        *,
        timeout_ms: int = 5000,
        args: list[str] | None = None,
    ) -> None:
        self.language = language
        self.repo_root = repo_root.resolve()
        self.binary = binary
        self.timeout_ms = timeout_ms
        self.args = args or self._default_args(binary)
        self._proc: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._pending: dict[Any, dict[str, Any]] = {}
        self._next_id = 1
        self._available: bool | None = None
        self._initialized = False
        self._failed = False
        self._opened: set[str] = set()

    @staticmethod
    def _default_args(binary: str) -> list[str]:
        if binary == "typescript-language-server":
            return ["--stdio"]
        if binary == "pyright-langserver":
            return ["--stdio"]
        if binary == "pylsp":
            return []
        if binary == "gopls":
            return ["serve"]
        if binary == "clangd":
            return []
        if binary == "rust-analyzer":
            return []
        return ["--stdio"] if "language-server" in binary else []

    def is_available(self) -> bool:
        if self._failed:
            return False
        if self._available is not None:
            return self._available
        try:
            self._ensure_server()
            self._available = self._initialized
        except Exception as exc:  # noqa: BLE001
            logger.info("LSP %s unavailable: %s", self.binary, exc)
            self._available = False
            self._failed = True
        return bool(self._available)

    def _ensure_server(self) -> None:
        with self._lock:
            if self._proc is not None and self._initialized:
                return
            self._proc = subprocess.Popen(
                [self.binary, *self.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                cwd=str(self.repo_root),
                bufsize=0,
            )
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()
            root_uri = self.repo_root.as_uri()
            result = self._request(
                "initialize",
                {
                    "processId": None,
                    "rootUri": root_uri,
                    "capabilities": {
                        "textDocument": {
                            "callHierarchy": {"dynamicRegistration": False},
                            "definition": {"linkSupport": False},
                        },
                        "workspace": {"symbol": {"symbolKind": {}}},
                    },
                    "workspaceFolders": [{"uri": root_uri, "name": self.repo_root.name}],
                },
            )
            if result is None:
                self._failed = True
                self._initialized = False
                return
            self._notify("initialized", {})
            self._initialized = True

    def _read_loop(self) -> None:
        assert self._proc and self._proc.stdout
        stdout = self._proc.stdout
        while True:
            headers: dict[str, str] = {}
            while True:
                line = stdout.readline()
                if not line:
                    return
                line = line.strip()
                if not line:
                    break
                if ":" in line:
                    k, v = line.split(":", 1)
                    headers[k.strip().lower()] = v.strip()
            length = int(headers.get("content-length", "0"))
            if length <= 0:
                continue
            body = stdout.read(length)
            try:
                msg = json.loads(body)
            except json.JSONDecodeError:
                continue
            if "id" in msg and ("result" in msg or "error" in msg):
                with self._lock:
                    self._pending[msg["id"]] = msg

    def _send(self, payload: dict[str, Any]) -> None:
        assert self._proc and self._proc.stdin
        data = json.dumps(payload)
        msg = f"Content-Length: {len(data.encode())}\r\n\r\n{data}"
        self._proc.stdin.write(msg)
        self._proc.stdin.flush()

    def _request(self, method: str, params: dict[str, Any]) -> Any | None:
        with self._lock:
            req_id = self._next_id
            self._next_id += 1
            self._pending.pop(req_id, None)
            self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
        # wait
        import time

        deadline = time.time() + (self.timeout_ms / 1000.0)
        while time.time() < deadline:
            with self._lock:
                if req_id in self._pending:
                    msg = self._pending.pop(req_id)
                    if "error" in msg:
                        return None
                    return msg.get("result")
            time.sleep(0.01)
        return None

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        with self._lock:
            self._send({"jsonrpc": "2.0", "method": method, "params": params})

    def _uri(self, rel: str) -> str:
        return (self.repo_root / rel).resolve().as_uri()

    def _did_open(self, rel: str) -> None:
        if rel in self._opened:
            return
        path = self.repo_root / rel
        if not path.is_file():
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        lang_id = {
            "python": "python",
            "javascript": "javascript",
            "typescript": "typescript",
            "go": "go",
            "c": "c",
            "cpp": "cpp",
            "rust": "rust",
            "java": "java",
        }.get(self.language, self.language)
        self._notify(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": self._uri(rel),
                    "languageId": lang_id,
                    "version": 1,
                    "text": text,
                }
            },
        )
        self._opened.add(rel)

    def find_symbol(self, name: str, file_hint: str | None) -> list[SymbolRef]:
        if not self.is_available():
            return []
        result = self._request("workspace/symbol", {"query": name})
        if not result:
            return []
        out: list[SymbolRef] = []
        short = name.split(".")[-1]
        for item in result:
            item_name = item.get("name", "")
            if item_name != short and item_name != name:
                continue
            loc = item.get("location") or {}
            uri = loc.get("uri", "")
            rng = loc.get("range") or {}
            start = rng.get("start", {}).get("line", 0) + 1
            end = rng.get("end", {}).get("line", start - 1) + 1
            rel = self._uri_to_rel(uri)
            if file_hint and rel != file_hint:
                continue
            kind = self._symbol_kind(item.get("kind"))
            out.append(
                SymbolRef(
                    name=item_name,
                    kind=kind,  # type: ignore[arg-type]
                    file=rel,
                    line_start=start,
                    line_end=end,
                    language=self.language,
                )
            )
        return out

    def find_imports(self, file_path: str) -> list[ImportEdge]:
        return []

    def find_callers(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        if not self.is_available():
            return []
        defs = self.find_symbol(symbol, file_hint)
        if not defs:
            return []
        d = defs[0]
        self._did_open(d.file)
        item = self._request(
            "textDocument/prepareCallHierarchy",
            {
                "textDocument": {"uri": self._uri(d.file)},
                "position": {"line": d.line_start - 1, "character": 0},
            },
        )
        if not item:
            return []
        if isinstance(item, list):
            if not item:
                return []
            item = item[0]
        incoming = self._request("callHierarchy/incomingCalls", {"item": item}) or []
        edges: list[CallEdge] = []
        for call in incoming:
            from_item = call.get("from") or {}
            uri = from_item.get("uri", "")
            rel = self._uri_to_rel(uri)
            name = from_item.get("name", "<unknown>")
            ranges = call.get("fromRanges") or []
            line = (ranges[0].get("start", {}).get("line", 0) + 1) if ranges else 1
            caller = SymbolRef(
                name=name,
                kind="function",
                file=rel,
                line_start=line,
                line_end=line,
                language=self.language,
            )
            edges.append(CallEdge(caller=caller, callee_name=symbol, call_site_line=line))
        return edges

    def find_callees(self, symbol: str, file_hint: str | None) -> list[CallEdge]:
        if not self.is_available():
            return []
        defs = self.find_symbol(symbol, file_hint)
        if not defs:
            return []
        d = defs[0]
        self._did_open(d.file)
        item = self._request(
            "textDocument/prepareCallHierarchy",
            {
                "textDocument": {"uri": self._uri(d.file)},
                "position": {"line": d.line_start - 1, "character": 0},
            },
        )
        if not item:
            return []
        if isinstance(item, list):
            if not item:
                return []
            item = item[0]
        outgoing = self._request("callHierarchy/outgoingCalls", {"item": item}) or []
        edges: list[CallEdge] = []
        for call in outgoing:
            to_item = call.get("to") or {}
            name = to_item.get("name", "")
            ranges = call.get("fromRanges") or []
            line = (ranges[0].get("start", {}).get("line", 0) + 1) if ranges else d.line_start
            edges.append(CallEdge(caller=d, callee_name=name, call_site_line=line))
        return edges

    def build_whole_program_graph(self, scope: str) -> WholeProgramGraph | None:
        return None

    def _uri_to_rel(self, uri: str) -> str:
        if uri.startswith("file://"):
            path = Path(uri[7:])
            try:
                return str(path.resolve().relative_to(self.repo_root)).replace("\\", "/")
            except ValueError:
                return str(path)
        return uri

    @staticmethod
    def _symbol_kind(kind: Any) -> str:
        # LSP SymbolKind
        mapping = {
            5: "class",
            6: "method",
            12: "function",
            11: "interface",
            23: "struct",
            13: "variable",
            14: "constant",
        }
        return mapping.get(int(kind or 12), "function")

    def shutdown(self) -> None:
        if self._proc is None:
            return
        try:
            self._request("shutdown", {})
            self._notify("exit", {})
        except Exception:  # noqa: BLE001
            pass
        try:
            self._proc.terminate()
        except Exception:  # noqa: BLE001
            pass
        self._proc = None
        self._initialized = False
