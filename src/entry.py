"""Process entry: launch the Ink TUI (Node) against the Python JSON-RPC runtime."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

from src import __version__

_REPO_ROOT = Path(__file__).resolve().parents[1]
_TUI_DIR = _REPO_ROOT / "tui"


def _find_node() -> str:
    node = shutil.which("node")
    if not node:
        raise SystemExit(
            "Node.js (>=20) is required to run the Neutrino TUI.\n"
            "Install Node, then: cd tui && npm install && npm run build"
        )
    return node


def _tui_entry() -> Path:
    dist = _TUI_DIR / "dist" / "index.js"
    if dist.is_file():
        return dist
    # Dev fallback via tsx
    tsx = _TUI_DIR / "node_modules" / ".bin" / "tsx"
    src = _TUI_DIR / "src" / "index.tsx"
    if tsx.is_file() and src.is_file():
        return src
    raise SystemExit(
        "Ink TUI is not built.\n"
        f"  cd {_TUI_DIR} && npm install && npm run build\n"
        "Then re-run: neutrino"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="neutrino",
        description="Neutrino: repo-aware coding agent (Ink TUI). "
        "Repository root defaults to the current working directory.",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit.",
    )
    parser.add_argument(
        "--cwd",
        type=Path,
        default=None,
        help="Repository / working directory for the runtime (default: cwd).",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose Python runtime logging (stderr).",
    )
    # Accept unknown for forward-compat with future TUI flags
    args, rest = parser.parse_known_args()
    if args.version:
        print(__version__)
        sys.exit(0)

    node = _find_node()
    entry = _tui_entry()
    cwd = str((args.cwd or Path.cwd()).resolve())

    cmd: list[str]
    if entry.suffix == ".tsx":
        tsx = str(_TUI_DIR / "node_modules" / ".bin" / "tsx")
        cmd = [tsx, str(entry), "--cwd", cwd, *rest]
    else:
        cmd = [node, str(entry), "--cwd", cwd, *rest]

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")
    # Prefer current interpreter for the child RPC process
    env.setdefault("NEUTRINO_PYTHON", sys.executable)
    if args.verbose:
        env["NEUTRINO_RPC_VERBOSE"] = "1"

    raise SystemExit(subprocess.call(cmd, env=env, cwd=str(_REPO_ROOT)))


if __name__ == "__main__":
    main()
