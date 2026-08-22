"""Process-wide logging configuration for the Neutrino runtime."""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

LogLevelName = Literal["debug", "info", "warning", "error"]

_LEVELS: dict[str, int] = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
}

_FORMAT = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")


def resolve_log_level(
    *,
    cli_level: str | None = None,
    verbose: bool = False,
) -> int:
    """Resolve log level from CLI, then env, then defaults.

    Precedence: ``--log-level`` > ``-v``/``--verbose`` > ``NEUTRINO_LOG_LEVEL`` > WARNING.
    """
    if cli_level:
        return _LEVELS.get(cli_level.strip().lower(), logging.WARNING)
    if verbose or os.environ.get("NEUTRINO_RPC_VERBOSE", "").strip() in {"1", "true", "yes"}:
        return logging.DEBUG
    env = (os.environ.get("NEUTRINO_LOG_LEVEL") or "").strip().lower()
    if env in _LEVELS:
        return _LEVELS[env]
    return logging.WARNING


def configure_logging(level: int, *, log_file: Path | str | None = None) -> None:
    """Send runtime logs to stderr (and optionally append to a file).

    When ``level`` is DEBUG and ``log_file`` is set (typically ``<repo>/logs.txt``),
    every log line is also appended to that file for offline debugging.
    """
    root = logging.getLogger()
    # Avoid duplicate stderr handlers when tests / re-entry call this.
    if not any(
        isinstance(h, logging.StreamHandler)
        and getattr(h, "stream", None) is sys.stderr
        and not isinstance(h, logging.FileHandler)
        for h in root.handlers
    ):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(_FORMAT)
        root.addHandler(handler)
    root.setLevel(level)

    if level <= logging.DEBUG and log_file is not None:
        _attach_debug_file(root, Path(log_file))

    # Keep noisy third-party libs quieter unless we are deep-debugging.
    if level > logging.DEBUG:
        logging.getLogger("httpx").setLevel(logging.WARNING)
        logging.getLogger("httpcore").setLevel(logging.WARNING)
        logging.getLogger("urllib3").setLevel(logging.WARNING)


def _attach_debug_file(root: logging.Logger, path: Path) -> None:
    resolved = path.expanduser().resolve()
    existing = [
        h
        for h in root.handlers
        if isinstance(h, logging.FileHandler) and Path(h.baseFilename).resolve() == resolved
    ]
    if existing:
        return
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("a", encoding="utf-8") as fh:
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S %Z")
        fh.write(f"\n----- neutrino debug session {stamp} -----\n")
    file_handler = logging.FileHandler(resolved, mode="a", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(_FORMAT)
    root.addHandler(file_handler)
    logging.getLogger("neutrino").info("debug log file: %s", resolved)
