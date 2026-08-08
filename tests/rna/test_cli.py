"""CLI argument parsing tests."""

from __future__ import annotations

import json

from src.rna.cli import _build_parser, main


def test_repo_after_subcommand_parses() -> None:
    parser = _build_parser()
    args = parser.parse_args(
        ["get-symbol", "parse_request", "--repo", "/tmp/repo", "--file-hint", "a.py"]
    )
    assert args.command == "get-symbol"
    assert str(args.repo) == "/tmp/repo"
    assert args.name == "parse_request"
    assert args.file_hint == "a.py"


def test_serve_repo_stdio_parses() -> None:
    parser = _build_parser()
    args = parser.parse_args(["serve", "--repo", ".", "--stdio"])
    assert args.command == "serve"
    assert args.stdio is True


def test_get_symbol_cli(python_repo, capsys) -> None:
    code = main(
        [
            "get-symbol",
            "parse_request",
            "--repo",
            str(python_repo),
            "--file-hint",
            "pkg/parser.py",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["data"]
    assert payload["data"][0]["name"] == "parse_request"
