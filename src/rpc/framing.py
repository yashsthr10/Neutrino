"""Newline-delimited JSON framing with a thread-safe stdout writer."""

from __future__ import annotations

import json
import threading
from typing import Any, TextIO


class NdjsonWriter:
    """Serialize JSON objects as NDJSON to a stream (typically stdout)."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def write(self, message: dict[str, Any]) -> None:
        line = json.dumps(message, default=str, separators=(",", ":"))
        with self._lock:
            self._stream.write(line + "\n")
            self._stream.flush()


def read_messages(stream: TextIO):
    """Yield parsed JSON objects from an NDJSON text stream."""
    for raw in stream:
        line = raw.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue
