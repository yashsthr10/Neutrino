"""CLI: `rna serve`, `rna warm`, and quick one-shot queries."""

from __future__ import annotations

import argparse
import json
import socketserver
import sys
from pathlib import Path

from src.rna.config import RnaConfig
from src.rna.facade import Rna
from src.rna.mcp.server import RnaMcpServer


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rna", description="RNA Research & Analysis engine")
    # Shared options live on a parent so they work after the subcommand too:
    #   rna serve --repo . --stdio
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="Repository root (default: current directory)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", parents=[common], help="Start MCP server")
    serve.add_argument(
        "--stdio",
        action="store_true",
        help="Serve over stdio (default when --port is omitted)",
    )
    serve.add_argument(
        "--port",
        type=int,
        default=None,
        help="Serve newline JSON-RPC over TCP port",
    )
    serve.add_argument("--web", action="store_true", help="Enable web search")

    warm = sub.add_parser("warm", parents=[common], help="Warm caches (embeddings)")
    warm.add_argument("--only", choices=["embeddings"], default="embeddings")

    get_symbol = sub.add_parser("get-symbol", parents=[common], help="One-shot get_symbol")
    get_symbol.add_argument("name")
    get_symbol.add_argument("--file-hint")

    get_file = sub.add_parser("get-file", parents=[common], help="One-shot get_file")
    get_file.add_argument("path")

    search = sub.add_parser("search", parents=[common], help="One-shot search")
    search.add_argument("query")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    cfg = RnaConfig(repo_path=repo, web_search_enabled=bool(getattr(args, "web", False)))
    rna = Rna(cfg)

    if args.command == "serve":
        server = RnaMcpServer(rna)
        if args.port is not None:
            return _serve_tcp(server, args.port)
        # stdio is the default transport
        server.serve_stdio()
        return 0

    if args.command == "warm":
        rna.warm(only=args.only)
        print(json.dumps({"ok": True, "only": args.only}))
        return 0

    if args.command == "get-symbol":
        result = rna.get_symbol(args.name, file_hint=args.file_hint)
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0

    if args.command == "get-file":
        result = rna.get_file(args.path)
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0

    if args.command == "search":
        result = rna.search(args.query)
        print(json.dumps(result.to_dict(), indent=2, default=str))
        return 0

    return 1


def _serve_tcp(server: RnaMcpServer, port: int) -> int:
    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for raw in self.rfile:
                line = raw.decode().strip()
                if not line:
                    continue
                try:
                    message = json.loads(line)
                except json.JSONDecodeError:
                    continue
                response = server.handle(message)
                if response is not None:
                    self.wfile.write((json.dumps(response) + "\n").encode())
                    self.wfile.flush()

    with socketserver.ThreadingTCPServer(("127.0.0.1", port), Handler) as httpd:
        print(f"rna MCP listening on 127.0.0.1:{port}", file=sys.stderr)
        httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
