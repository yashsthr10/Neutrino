"""Process entry: launch flags, then Textual TUI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src import __version__
from src.config import apply_launch_overrides, load_merged_settings
from src.tui.app import NeutrinoApp


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="neutrino",
        description="Neutrino: repo-aware coding agent (Textual TUI). "
        "Repository root is always the current working directory.",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Explicit path to a TOML config file.",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Verbose logging (maps to settings).",
    )
    parser.add_argument(
        "--version",
        action="store_true",
        help="Print version and exit.",
    )
    parser.add_argument(
        "--layout",
        choices=("single", "split"),
        default=None,
        help="TUI layout: single column (default) or split with side panel.",
    )
    args = parser.parse_args()
    if args.version:
        print(__version__)
        sys.exit(0)

    settings = load_merged_settings(config_path=args.config)
    if args.verbose:
        settings = apply_launch_overrides(settings, verbose=True)
    if args.layout is not None:
        settings = apply_launch_overrides(settings, layout=args.layout)

    app = NeutrinoApp(settings)
    app.run()


if __name__ == "__main__":
    main()
