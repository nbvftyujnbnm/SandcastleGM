"""Save and restore a session to/from JSON.

A saved session bundles the full :class:`GameState` and its :class:`EventLog`,
so a campaign can be stored between sessions and reopened where it left off. The
LLM provider/conversation is not persisted — on reload the GM continues from the
restored state and the event log (the story so far), which is what the next turn
is built from anyway.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from sandcastlegm.core.events import EventLog
from sandcastlegm.core.state import GameState

DEFAULT_DIR = os.environ.get("SANDCASTLEGM_SAVE_DIR", "sessions")
FORMAT_VERSION = 1


def to_payload(state: GameState, log: EventLog) -> dict[str, Any]:
    return {"version": FORMAT_VERSION, "state": state.to_dict(), "events": log.to_list()}


def from_payload(payload: dict[str, Any]) -> tuple[GameState, EventLog]:
    state = GameState.from_dict(payload["state"])
    log = EventLog()
    log.load(payload.get("events", []))
    return state, log


def save_session(state: GameState, log: EventLog, path: str | os.PathLike) -> str:
    """Write a session to ``path``. Returns the path written."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(to_payload(state, log), ensure_ascii=False, indent=2), encoding="utf-8")
    return str(p)


def save_session_to_dir(state: GameState, log: EventLog, directory: str | os.PathLike = DEFAULT_DIR) -> str:
    """Save using the game id as the filename under ``directory``."""
    return save_session(state, log, Path(directory) / f"{state.id}.json")


def load_session(path: str | os.PathLike) -> tuple[GameState, EventLog]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return from_payload(payload)
