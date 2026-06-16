"""Virtual-tabletop adapter interface.

Multiplayer play happens on a shared board. Rather than build one renderer, the
GM system exports its state into the formats popular open virtual tabletops
already understand, so groups can keep using the tools they like. An adapter
translates :class:`~sandcastlegm.core.state` objects into one VTT's import
format; the built-in multiplayer server is just another consumer of the same
state and can coexist with these.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sandcastlegm.core.state import Character, GameState, MapGrid


class VTTAdapter(ABC):
    id: str = "base"
    name: str = "Base VTT"

    @abstractmethod
    def export_character(self, character: Character) -> Any:
        """Translate a character sheet into the VTT's import payload."""

    @abstractmethod
    def export_map(self, grid: MapGrid) -> Any:
        """Translate a tactical map into the VTT's import payload."""

    def export_session(self, state: GameState) -> Any:
        """Translate the whole session. Default: a dict of the pieces."""
        return {
            "characters": [self.export_character(c) for c in state.characters.values()],
            "maps": [self.export_map(m) for m in state.maps.values()],
        }
