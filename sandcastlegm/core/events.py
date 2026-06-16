"""The session event log.

Everything the table sees — narration, dice rolls, map changes, turn changes —
is an :class:`Event`. The log is the single source of truth that gets broadcast
to every connected player and replayed to reconstruct a session.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class EventType(str, Enum):
    NARRATION = "narration"      # GM prose
    DIALOGUE = "dialogue"        # an NPC speaking
    PLAYER_ACTION = "player_action"
    ROLL = "roll"                # a dice resolution
    SCENE = "scene"              # a new/changed scene
    MAP = "map"                  # a map or token change
    TURN = "turn"                # initiative / turn change
    SYSTEM = "system"            # joins, errors, meta


@dataclass
class Event:
    type: EventType
    text: str = ""
    actor: str | None = None  # character or player id, when applicable
    data: dict[str, Any] = field(default_factory=dict)  # structured payload
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ts": self.ts,
            "type": self.type.value,
            "text": self.text,
            "actor": self.actor,
            "data": self.data,
        }


class EventLog:
    """An append-only log with optional subscribers for live broadcast."""

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._subscribers: list[Any] = []  # callables: (Event) -> None

    def append(self, event: Event) -> Event:
        self._events.append(event)
        for sub in list(self._subscribers):
            sub(event)
        return event

    def subscribe(self, callback: Any) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Any) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    @property
    def events(self) -> list[Event]:
        return list(self._events)

    def since(self, ts: float) -> list[Event]:
        return [e for e in self._events if e.ts > ts]

    def to_list(self) -> list[dict[str, Any]]:
        return [e.to_dict() for e in self._events]
