"""The Game Master's tool surface.

These are the structured actions the AI GM takes to *do* things to the game
beyond narrating: resolve checks, manage scenes, draw and update the tactical
map, spawn NPCs, track hit points and initiative. Each tool both mutates the
:class:`~sandcastlegm.core.state.GameState` and appends an
:class:`~sandcastlegm.core.events.Event` so every connected player sees the
change. Narration itself is plain assistant text — only state changes are tools,
which keeps the dice and the board authoritative rather than improvised.

The tool JSON schemas (``TOOL_SPECS``) are model-agnostic; the same definitions
feed the Anthropic tool-use loop and the deterministic fallback referee.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sandcastlegm.core.events import Event, EventLog, EventType
from sandcastlegm.core.state import (
    GameState,
    MapGrid,
    Position,
    Scene,
    Token,
    TokenKind,
)
from sandcastlegm.rulesets.base import CheckRequest, Ruleset


@dataclass
class GMContext:
    """Everything a tool needs to read and change the game."""

    ruleset: Ruleset
    state: GameState
    log: EventLog


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "roll_check",
        "description": (
            "Resolve an uncertain action with the ruleset's dice mechanic. Use this "
            "for anything that could fail. Never decide the result yourself."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "actor_id": {"type": "string", "description": "Character id attempting the action."},
                "ability": {"type": "string", "description": "Ability key, e.g. STR/DEX/CON/PER/WIL/CHA."},
                "skill": {"type": "string", "description": "Skill applied, if any."},
                "target_number": {"type": "integer", "description": "Difficulty (TN). Omit for the ruleset default."},
                "modifiers": {
                    "type": "object",
                    "description": "Situational modifiers as label -> integer.",
                    "additionalProperties": {"type": "integer"},
                },
                "description": {"type": "string", "description": "What the actor is attempting."},
            },
            "required": ["description"],
        },
    },
    {
        "name": "roll_dice",
        "description": "Roll an arbitrary dice expression (e.g. '2d6+1', '1d3') for damage or random tables.",
        "input_schema": {
            "type": "object",
            "properties": {
                "expression": {"type": "string"},
                "reason": {"type": "string"},
            },
            "required": ["expression"],
        },
    },
    {
        "name": "set_scene",
        "description": "Establish or change the current scene: title, narrative, location, present NPCs and exits.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "narrative": {"type": "string"},
                "location": {"type": "string"},
                "present_npcs": {"type": "array", "items": {"type": "string"}},
                "exits": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["title"],
        },
    },
    {
        "name": "create_map",
        "description": "Create a tactical map grid for the current scene and make it active.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "width": {"type": "integer"},
                "height": {"type": "integer"},
                "walls": {
                    "type": "array",
                    "description": "Wall cells as [x, y] pairs.",
                    "items": {"type": "array", "items": {"type": "integer"}},
                },
            },
            "required": ["name", "width", "height"],
        },
    },
    {
        "name": "place_token",
        "description": "Place a token (character, monster, object) on the active map.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
                "kind": {"type": "string", "enum": [k.value for k in TokenKind]},
                "glyph": {"type": "string"},
                "character_id": {"type": "string"},
                "hidden": {"type": "boolean"},
            },
            "required": ["name", "x", "y"],
        },
    },
    {
        "name": "move_token",
        "description": "Move a token to a new cell on the active map.",
        "input_schema": {
            "type": "object",
            "properties": {
                "token_id": {"type": "string"},
                "x": {"type": "integer"},
                "y": {"type": "integer"},
            },
            "required": ["token_id", "x", "y"],
        },
    },
    {
        "name": "spawn_npc",
        "description": "Create an NPC or monster character sheet via the ruleset.",
        "input_schema": {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "level": {"type": "integer"},
                "combat_style": {"type": "string"},
                "abilities": {"type": "object", "additionalProperties": {"type": "integer"}},
            },
            "required": ["name"],
        },
    },
    {
        "name": "update_character",
        "description": "Change a character's hit points and conditions (damage, healing, status).",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "hp_delta": {"type": "integer", "description": "Negative for damage, positive for healing."},
                "add_conditions": {"type": "array", "items": {"type": "string"}},
                "remove_conditions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["character_id"],
        },
    },
    {
        "name": "set_turn_order",
        "description": "Begin a tactical encounter by setting initiative order (list of character ids).",
        "input_schema": {
            "type": "object",
            "properties": {"order": {"type": "array", "items": {"type": "string"}}},
            "required": ["order"],
        },
    },
    {
        "name": "advance_turn",
        "description": "Advance initiative to the next combatant.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "update_notes",
        "description": "Record private GM plot notes / hidden state (never shown to players).",
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string"},
                "value": {"type": "string"},
            },
            "required": ["key", "value"],
        },
    },
]


def tool_names() -> set[str]:
    return {spec["name"] for spec in TOOL_SPECS}


def execute_tool(ctx: GMContext, name: str, tool_input: dict[str, Any]) -> str:
    """Dispatch a tool call, mutate state, log an event, and return a result string."""
    handler = _HANDLERS.get(name)
    if handler is None:
        return f"error: unknown tool {name!r}"
    try:
        return handler(ctx, tool_input)
    except Exception as exc:  # noqa: BLE001 - surface tool errors back to the model
        return f"error: {type(exc).__name__}: {exc}"


# --- individual tool handlers --------------------------------------------------
def _roll_check(ctx: GMContext, ip: dict[str, Any]) -> str:
    req = CheckRequest(
        actor_id=ip.get("actor_id"),
        ability=ip.get("ability"),
        skill=ip.get("skill"),
        target_number=ip.get("target_number"),
        modifiers={k: int(v) for k, v in (ip.get("modifiers") or {}).items()},
        description=ip.get("description", ""),
    )
    result = ctx.ruleset.resolve_check(ctx.state, req)
    ctx.log.append(
        Event(
            type=EventType.ROLL,
            text=f"{req.description}: {result.describe()}",
            actor=req.actor_id,
            data=result.to_dict(),
        )
    )
    return json.dumps(result.to_dict(), ensure_ascii=False)


def _roll_dice(ctx: GMContext, ip: dict[str, Any]) -> str:
    result = ctx.ruleset.roller.roll(ip["expression"])
    text = result.describe()
    if ip.get("reason"):
        text = f"{ip['reason']}: {text}"
    ctx.log.append(Event(type=EventType.ROLL, text=text, data={"total": result.total}))
    return text


def _set_scene(ctx: GMContext, ip: dict[str, Any]) -> str:
    scene = Scene(
        title=ip["title"],
        narrative=ip.get("narrative", ""),
        location=ip.get("location", ""),
        present_npcs=list(ip.get("present_npcs", [])),
        exits=list(ip.get("exits", [])),
        tags=list(ip.get("tags", [])),
    )
    ctx.state.add_scene(scene)
    ctx.log.append(
        Event(type=EventType.SCENE, text=f"Scene: {scene.title}", data=scene.to_dict())
    )
    return f"scene set: {scene.id} — {scene.title}"


def _create_map(ctx: GMContext, ip: dict[str, Any]) -> str:
    grid = MapGrid(name=ip["name"], width=int(ip["width"]), height=int(ip["height"]))
    for cell in ip.get("walls", []) or []:
        x, y = int(cell[0]), int(cell[1])
        grid.terrain[f"{x},{y}"] = "wall"
    ctx.state.add_map(grid)
    scene = ctx.state.current_scene
    if scene is not None:
        scene.map_id = grid.id
    ctx.log.append(Event(type=EventType.MAP, text=f"Map created: {grid.name}", data=grid.to_dict()))
    return f"map created: {grid.id} ({grid.width}x{grid.height})"


def _active_map(ctx: GMContext) -> MapGrid:
    grid = ctx.state.active_map
    if grid is None:
        raise ValueError("no active map; call create_map first")
    return grid


def _place_token(ctx: GMContext, ip: dict[str, Any]) -> str:
    grid = _active_map(ctx)
    token = Token(
        name=ip["name"],
        position=Position(int(ip["x"]), int(ip["y"])),
        kind=TokenKind(ip.get("kind", "marker")),
        glyph=ip.get("glyph", ip["name"][:1] or "●"),
        character_id=ip.get("character_id"),
        hidden=bool(ip.get("hidden", False)),
    )
    grid.add_token(token)
    ctx.log.append(Event(type=EventType.MAP, text=f"{token.name} placed at ({token.position.x},{token.position.y})", data=token.to_dict()))
    return f"token placed: {token.id}"


def _move_token(ctx: GMContext, ip: dict[str, Any]) -> str:
    grid = _active_map(ctx)
    token = grid.move_token(ip["token_id"], int(ip["x"]), int(ip["y"]))
    ctx.log.append(Event(type=EventType.MAP, text=f"{token.name} moves to ({ip['x']},{ip['y']})", data=token.to_dict()))
    return f"token moved: {token.id} -> ({ip['x']},{ip['y']})"


def _spawn_npc(ctx: GMContext, ip: dict[str, Any]) -> str:
    char = ctx.ruleset.new_character(
        ip["name"],
        is_pc=False,
        level=ip.get("level", 1),
        combat_style=ip.get("combat_style", "ストライカー"),
        abilities=ip.get("abilities", {}),
    )
    ctx.state.add_character(char)
    ctx.log.append(Event(type=EventType.SYSTEM, text=f"NPC spawned: {char.name} ({char.id})", data={"id": char.id, "hp": char.hp}))
    return f"npc created: {char.id} (hp {char.hp})"


def _update_character(ctx: GMContext, ip: dict[str, Any]) -> str:
    char = ctx.state.characters.get(ip["character_id"])
    if char is None:
        raise ValueError(f"no character {ip['character_id']!r}")
    if "hp_delta" in ip and ip["hp_delta"] is not None:
        char.hp = max(0, min(char.max_hp, char.hp + int(ip["hp_delta"])))
    for cond in ip.get("add_conditions", []) or []:
        if cond not in char.conditions:
            char.conditions.append(cond)
    for cond in ip.get("remove_conditions", []) or []:
        if cond in char.conditions:
            char.conditions.remove(cond)
    downed = " (DOWNED)" if char.hp <= 0 else ""
    ctx.log.append(
        Event(
            type=EventType.SYSTEM,
            text=f"{char.name}: hp {char.hp}/{char.max_hp}{downed}",
            actor=char.id,
            data={"hp": char.hp, "max_hp": char.max_hp, "conditions": char.conditions},
        )
    )
    return f"{char.name}: hp {char.hp}/{char.max_hp}, conditions {char.conditions}"


def _set_turn_order(ctx: GMContext, ip: dict[str, Any]) -> str:
    ctx.state.turn_order.order = list(ip["order"])
    ctx.state.turn_order.round = 1
    ctx.state.turn_order.index = 0
    active = ctx.state.turn_order.active
    ctx.log.append(Event(type=EventType.TURN, text="Initiative set", data=ctx.state.turn_order.to_dict()))
    return f"turn order set; active: {active}"


def _advance_turn(ctx: GMContext, ip: dict[str, Any]) -> str:
    active = ctx.state.turn_order.advance()
    ctx.log.append(Event(type=EventType.TURN, text=f"Turn: {active}", data=ctx.state.turn_order.to_dict()))
    return f"now acting: {active} (round {ctx.state.turn_order.round})"


def _update_notes(ctx: GMContext, ip: dict[str, Any]) -> str:
    ctx.state.notes[ip["key"]] = ip["value"]
    return f"note recorded: {ip['key']}"


_HANDLERS = {
    "roll_check": _roll_check,
    "roll_dice": _roll_dice,
    "set_scene": _set_scene,
    "create_map": _create_map,
    "place_token": _place_token,
    "move_token": _move_token,
    "spawn_npc": _spawn_npc,
    "update_character": _update_character,
    "set_turn_order": _set_turn_order,
    "advance_turn": _advance_turn,
    "update_notes": _update_notes,
}
