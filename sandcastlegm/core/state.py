"""The game-state domain model.

These types are deliberately ruleset-agnostic. Anything system-specific (a
Sandcastle character's six ability values, a combat style, hit-point formula
output, …) lives in the free-form :attr:`Character.sheet` dict, which the active
ruleset owns and interprets. The core only knows the concepts every tabletop
session shares: scenes, a tactical map, tokens, characters, and a turn order.

Everything is a plain dataclass with ``to_dict`` so a whole session serialises
to JSON for persistence, network sync, and virtual-tabletop export.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


class TokenKind(str, Enum):
    PC = "pc"
    NPC = "npc"
    ENEMY = "enemy"
    OBJECT = "object"
    MARKER = "marker"


@dataclass
class Position:
    """A cell on the tactical grid (origin top-left, +x right, +y down)."""

    x: int
    y: int

    def to_dict(self) -> dict[str, Any]:
        return {"x": self.x, "y": self.y}


@dataclass
class Token:
    """A piece on the map: a character, a monster, a door, a marker."""

    name: str
    position: Position
    kind: TokenKind = TokenKind.MARKER
    id: str = field(default_factory=lambda: _new_id("tok"))
    size: int = 1  # footprint in cells (1 = single cell)
    glyph: str = "●"  # short label/emoji rendered on the board
    color: str = "#888888"
    character_id: str | None = None  # links a token to a Character sheet
    hidden: bool = False  # known to GM but not yet revealed to players

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        d["position"] = self.position.to_dict()
        return d


@dataclass
class MapGrid:
    """A tactical battle map: a rectangular grid plus the tokens on it.

    ``terrain`` is a sparse ``"x,y" -> tag`` map (e.g. ``"wall"``, ``"water"``,
    ``"difficult"``); unlisted cells are open floor.
    """

    name: str = "Map"
    width: int = 20
    height: int = 20
    cell_size_m: float = 1.5  # metres per cell (Sandcastle reach/move scale)
    terrain: dict[str, str] = field(default_factory=dict)
    tokens: dict[str, Token] = field(default_factory=dict)
    id: str = field(default_factory=lambda: _new_id("map"))

    def add_token(self, token: Token) -> Token:
        self.tokens[token.id] = token
        return token

    def move_token(self, token_id: str, x: int, y: int) -> Token:
        token = self.tokens[token_id]
        token.position = Position(x, y)
        return token

    def remove_token(self, token_id: str) -> None:
        self.tokens.pop(token_id, None)

    def render_ascii(self, reveal_hidden: bool = False) -> str:
        """A plain-text board, handy for CLI play and for showing the LLM the map."""
        grid = [["·" for _ in range(self.width)] for _ in range(self.height)]
        for key, tag in self.terrain.items():
            tx, ty = (int(v) for v in key.split(","))
            if 0 <= ty < self.height and 0 <= tx < self.width:
                grid[ty][tx] = "▓" if tag == "wall" else "≈" if tag == "water" else "░"
        for token in self.tokens.values():
            if token.hidden and not reveal_hidden:
                continue
            px, py = token.position.x, token.position.y
            if 0 <= py < self.height and 0 <= px < self.width:
                grid[py][px] = token.glyph[0]
        return "\n".join("".join(row) for row in grid)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "width": self.width,
            "height": self.height,
            "cell_size_m": self.cell_size_m,
            "terrain": dict(self.terrain),
            "tokens": {tid: t.to_dict() for tid, t in self.tokens.items()},
        }


@dataclass
class Scene:
    """A narrative beat: where the party is, what's happening, and the way out."""

    title: str
    narrative: str = ""
    location: str = ""
    present_npcs: list[str] = field(default_factory=list)
    exits: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    map_id: str | None = None  # the MapGrid in play for this scene, if any
    id: str = field(default_factory=lambda: _new_id("scn"))
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Character:
    """A participant. ``sheet`` holds ruleset-specific stats."""

    name: str
    is_pc: bool = True
    controller: str | None = None  # player/session id that controls this PC
    sheet: dict[str, Any] = field(default_factory=dict)
    hp: int = 0
    max_hp: int = 0
    conditions: list[str] = field(default_factory=list)
    inventory: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: _new_id("chr"))

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class TurnOrder:
    """Initiative tracking for tactical scenes."""

    order: list[str] = field(default_factory=list)  # character ids, acting order
    round: int = 0
    index: int = 0  # whose turn within the round

    @property
    def active(self) -> str | None:
        return self.order[self.index] if self.order else None

    def advance(self) -> str | None:
        if not self.order:
            return None
        self.index += 1
        if self.index >= len(self.order):
            self.index = 0
            self.round += 1
        return self.active

    def to_dict(self) -> dict[str, Any]:
        return {"order": list(self.order), "round": self.round, "index": self.index}


@dataclass
class GameState:
    """The complete, serialisable state of one campaign session."""

    ruleset_id: str
    title: str = "Untitled Session"
    characters: dict[str, Character] = field(default_factory=dict)
    maps: dict[str, MapGrid] = field(default_factory=dict)
    scenes: list[Scene] = field(default_factory=list)
    current_scene_id: str | None = None
    turn_order: TurnOrder = field(default_factory=TurnOrder)
    notes: dict[str, Any] = field(default_factory=dict)  # GM private notes/plot state
    id: str = field(default_factory=lambda: _new_id("game"))

    # --- convenience accessors -------------------------------------------------
    @property
    def current_scene(self) -> Scene | None:
        if self.current_scene_id is None:
            return None
        return next((s for s in self.scenes if s.id == self.current_scene_id), None)

    @property
    def active_map(self) -> MapGrid | None:
        scene = self.current_scene
        if scene and scene.map_id:
            return self.maps.get(scene.map_id)
        return None

    def add_character(self, character: Character) -> Character:
        self.characters[character.id] = character
        return character

    def add_scene(self, scene: Scene, make_current: bool = True) -> Scene:
        self.scenes.append(scene)
        if make_current:
            self.current_scene_id = scene.id
        return scene

    def add_map(self, grid: MapGrid) -> MapGrid:
        self.maps[grid.id] = grid
        return grid

    def player_characters(self) -> list[Character]:
        return [c for c in self.characters.values() if c.is_pc]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "ruleset_id": self.ruleset_id,
            "title": self.title,
            "characters": {cid: c.to_dict() for cid, c in self.characters.items()},
            "maps": {mid: m.to_dict() for mid, m in self.maps.items()},
            "scenes": [s.to_dict() for s in self.scenes],
            "current_scene_id": self.current_scene_id,
            "turn_order": self.turn_order.to_dict(),
            "notes": dict(self.notes),
        }
