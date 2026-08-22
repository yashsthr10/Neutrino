"""Run Neutrino JSON-RPC runtime on stdio: python -m src.rpc"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from src.rpc.framing import NdjsonWriter
from src.rpc.server import build_server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m src.rpc", description="Neutrino RPC runtime")
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repository root (default: cwd).",
    )
    parser.add_argument(
        "--model",
        default="default",
        help="Model label reported in session.hello.",
    )
    parser.add_argument(
        "--interactive-gates",
        action="store_true",
        help="Require explicit approval/recovery (default: auto).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging to stderr.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    repo = (args.repo or Path.cwd()).resolve()
    writer = NdjsonWriter(sys.stdout)
    server = build_server(
        repo,
        writer,
        model_name=args.model,
        auto_approve=not args.interactive_gates,
        auto_recover=not args.interactive_gates,
    )
    server.serve_stdio(sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
