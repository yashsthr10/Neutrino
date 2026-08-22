"""Logging config: stderr + optional logs.txt under the repo."""

from __future__ import annotations

import logging
from pathlib import Path

from src.logging_config import configure_logging


def test_debug_logging_appends_logs_txt(tmp_path: Path) -> None:
    log_path = tmp_path / "logs.txt"
    # Reset root handlers so the test is isolated.
    root = logging.getLogger()
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    configure_logging(logging.DEBUG, log_file=log_path)
    logging.getLogger("neutrino.agent").debug("llm.response sample payload")
    logging.getLogger("neutrino.agent").debug("tool.response sample payload")

    for handler in list(root.handlers):
        handler.flush()

    text = log_path.read_text(encoding="utf-8")
    assert "neutrino debug session" in text
    assert "llm.response sample payload" in text
    assert "tool.response sample payload" in text
    assert "debug log file:" in text
