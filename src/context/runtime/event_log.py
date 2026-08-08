"""EventLog — append-only structured event trace for one execution."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True, slots=True)
class Event:
    kind: str
    payload: dict
    at: str


@dataclass(frozen=True, slots=True)
class EventLog:
    events: tuple[Event, ...] = ()

    def append(self, kind: str, payload: dict, *, at: str | None = None) -> EventLog:
        event = Event(kind=kind, payload=payload, at=at or _now_iso())
        return EventLog(events=self.events + (event,))
