"""Core domain: dice, game state, and the event log. No external dependencies."""

from sandcastlegm.core.dice import (
    DiceRoller,
    DieRoll,
    RollResult,
    sandcastle_roller,
)
from sandcastlegm.core.events import Event, EventLog, EventType
from sandcastlegm.core.state import (
    Character,
    GameState,
    MapGrid,
    Position,
    Scene,
    Token,
    TokenKind,
    TurnOrder,
)

__all__ = [
    "DiceRoller",
    "DieRoll",
    "RollResult",
    "sandcastle_roller",
    "Event",
    "EventLog",
    "EventType",
    "Character",
    "GameState",
    "MapGrid",
    "Position",
    "Scene",
    "Token",
    "TokenKind",
    "TurnOrder",
]
