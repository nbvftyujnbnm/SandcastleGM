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
        "name": "spawn_monster",
        "description": (
            "Spawn a statted monster from the ruleset's bestiary by key (see the "
            "ruleset guidance for keys). Optionally rename or spawn several. For a "
            "creature not in the bestiary, use spawn_npc instead."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "key": {"type": "string", "description": "Bestiary key, e.g. brown_bear."},
                "name": {"type": "string", "description": "Optional display name override."},
                "count": {"type": "integer", "description": "How many to spawn (default 1)."},
            },
            "required": ["key"],
        },
    },
    {
        "name": "resolve_attack",
        "description": (
            "Resolve one attack end-to-end: roll to-hit (3d6 + attack bonus) vs the "
            "target's defense, and on a hit roll damage and apply it to the target's "
            "HP automatically. Prefer this over chaining roll_check + update_character "
            "for combat. Provide attack_name for a monster's listed attack, or att and "
            "damage explicitly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "attacker_id": {"type": "string"},
                "target_id": {"type": "string"},
                "attack_name": {"type": "string", "description": "Named attack on the attacker's sheet."},
                "att": {"type": "integer", "description": "Attack bonus, if not using a named attack."},
                "damage": {"type": "string", "description": "Damage dice, e.g. '1d6+2'."},
                "modifier": {"type": "integer", "description": "Situational to-hit modifier."},
            },
            "required": ["target_id"],
        },
    },
    {
        "name": "apply_effect",
        "description": (
            "Apply a status effect (hex, buff, debuff) to a character. Modifiers are "
            "applied automatically: 'check' to its ability checks, 'attack' to its "
            "attack rolls, 'defense' to its defense. Pass a 'hex' key to use a "
            "ruleset-defined effect, or 'mods' to set them explicitly."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "name": {"type": "string", "description": "Effect name (defaults to the hex key)."},
                "hex": {"type": "string", "description": "Ruleset hex key (see guidance)."},
                "mods": {"type": "object", "additionalProperties": {"type": "integer"},
                         "description": "Explicit modifiers, e.g. {\"attack\": -2}."},
                "rounds": {"type": "integer", "description": "Duration in rounds (informational)."},
            },
            "required": ["character_id"],
        },
    },
    {
        "name": "clear_effect",
        "description": "Remove a status effect from a character by name.",
        "input_schema": {
            "type": "object",
            "properties": {
                "character_id": {"type": "string"},
                "name": {"type": "string"},
            },
            "required": ["character_id", "name"],
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
        "name": "roll_initiative",
        "description": (
            "Start combat by rolling initiative and setting the turn order. Uses "
            "the ruleset's rule (Sandcastle: each side rolls 1d6, higher goes "
            "first, ties favour PCs). Omit combatant_ids to include everyone."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "combatant_ids": {"type": "array", "items": {"type": "string"},
                                  "description": "Character ids in the fight; default = all."}
            },
        },
    },
    {
        "name": "set_turn_order",
        "description": "Set the initiative order explicitly (list of character ids), e.g. when players choose their own order.",
        "input_schema": {
            "type": "object",
            "properties": {"order": {"type": "array", "items": {"type": "string"}}},
            "required": ["order"],
        },
    },
    {
        "name": "advance_turn",
        "description": "Advance initiative to the next living combatant (downed combatants are skipped). Increments the round when it wraps.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "end_combat",
        "description": "End the encounter and clear the initiative order.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "rest",
        "description": (
            "Take a rest: restore HP and PP to maximum and clear status effects "
            "and conditions (Sandcastle: a week's rest fully heals). Defaults to "
            "all player characters; pass character_ids to choose, or all=true."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "character_ids": {"type": "array", "items": {"type": "string"}},
                "all": {"type": "boolean", "description": "Include NPCs/enemies too."},
            },
        },
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


# --- argument coercion ---------------------------------------------------------
# Different models serialise structured arguments differently (a real object, a
# JSON string, or a list of key/value pairs). These helpers accept them all so a
# tool call from any provider lands the same way.
def _as_int_map(value: Any) -> dict[str, int]:
    if not value:
        return {}
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    if isinstance(value, dict):
        return {str(k): int(v) for k, v in value.items()}
    if isinstance(value, list):
        out: dict[str, int] = {}
        for item in value:
            if isinstance(item, dict):
                k = item.get("key") or item.get("label") or item.get("name")
                v = item.get("value")
                if k is not None and v is not None:
                    out[str(k)] = int(v)
        return out
    return {}


def _as_pairs(value: Any) -> list:
    if not value:
        return []
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return []
    return value if isinstance(value, list) else []


# --- individual tool handlers --------------------------------------------------
def _roll_check(ctx: GMContext, ip: dict[str, Any]) -> str:
    req = CheckRequest(
        actor_id=ip.get("actor_id"),
        ability=ip.get("ability"),
        skill=ip.get("skill"),
        target_number=ip.get("target_number"),
        modifiers=_as_int_map(ip.get("modifiers")),
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
    for cell in _as_pairs(ip.get("walls")):
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
        abilities=_as_int_map(ip.get("abilities")),
    )
    ctx.state.add_character(char)
    ctx.log.append(Event(type=EventType.SYSTEM, text=f"NPC spawned: {char.name} ({char.id})", data={"id": char.id, "hp": char.hp}))
    return f"npc created: {char.id} (hp {char.hp})"


def _spawn_monster(ctx: GMContext, ip: dict[str, Any]) -> str:
    key = ip["key"]
    count = max(1, int(ip.get("count", 1) or 1))
    catalog = ctx.ruleset.monster_catalog()
    if key not in catalog:
        return f"error: unknown monster {key!r}; available: {sorted(catalog)}"
    created = []
    for i in range(count):
        name = ip.get("name")
        if name and count > 1:
            name = f"{name}{i + 1}"
        elif count > 1:
            name = f"{catalog[key]}{i + 1}"
        char = ctx.ruleset.create_monster(key, name=name)
        ctx.state.add_character(char)
        created.append(char)
        ctx.log.append(Event(
            type=EventType.SYSTEM,
            text=f"モンスター出現: {char.name}（{char.id}, hp {char.hp}, 防御 {char.sheet.get('defense')}）",
            data={"id": char.id, "hp": char.hp, "monster_key": key},
        ))
    ids = ", ".join(c.id for c in created)
    return f"spawned {count}x {catalog[key]}: {ids}"


def _resolve_attack(ctx: GMContext, ip: dict[str, Any]) -> str:
    result = ctx.ruleset.resolve_attack(
        ctx.state,
        ip.get("attacker_id"),
        ip["target_id"],
        att=ip.get("att"),
        damage=ip.get("damage"),
        attack_name=ip.get("attack_name"),
        modifier=int(ip.get("modifier", 0) or 0),
    )
    target = ctx.state.characters[ip["target_id"]]
    downed = False
    if result.hit and result.damage:
        target.hp = max(0, target.hp - result.damage)
        if target.hp <= 0 and "戦闘不能" not in target.conditions:
            target.conditions.append("戦闘不能")
            downed = True
    suffix = f" → {target.name} hp {target.hp}/{target.max_hp}" + (" (戦闘不能)" if downed else "")
    ctx.log.append(
        Event(
            type=EventType.ROLL,
            text=result.describe() + suffix,
            actor=result.attacker_id,
            data={**result.to_dict(), "target_hp": target.hp, "target_max_hp": target.max_hp},
        )
    )
    return json.dumps({**result.to_dict(), "target_hp": target.hp}, ensure_ascii=False)


def _apply_effect(ctx: GMContext, ip: dict[str, Any]) -> str:
    char = ctx.state.characters.get(ip["character_id"])
    if char is None:
        raise ValueError(f"no character {ip['character_id']!r}")
    hex_key = ip.get("hex")
    name = ip.get("name") or hex_key
    if not name:
        return "error: provide a name or hex"
    mods = _as_int_map(ip.get("mods"))
    if not mods and hex_key:
        mods = {k: int(v) for k, v in ctx.ruleset.hex_catalog().get(hex_key, {}).items()}
    rounds = ip.get("rounds")
    effects = char.sheet.setdefault("effects", [])
    effects[:] = [e for e in effects if e.get("name") != name]  # replace same-named
    effects.append({"name": name, "mods": mods, "rounds": rounds})
    if name not in char.conditions:
        char.conditions.append(name)
    mod_str = ", ".join(f"{k}{v:+d}" for k, v in mods.items()) or "効果なし"
    ctx.log.append(Event(
        type=EventType.SYSTEM,
        text=f"{char.name} に効果「{name}」({mod_str})" + (f" {rounds}ラウンド" if rounds else ""),
        actor=char.id, data={"effect": name, "mods": mods, "rounds": rounds},
    ))
    return f"applied {name} to {char.name}: {mod_str}"


def _clear_effect(ctx: GMContext, ip: dict[str, Any]) -> str:
    char = ctx.state.characters.get(ip["character_id"])
    if char is None:
        raise ValueError(f"no character {ip['character_id']!r}")
    name = ip["name"]
    char.sheet["effects"] = [e for e in char.sheet.get("effects", []) if e.get("name") != name]
    if name in char.conditions:
        char.conditions.remove(name)
    ctx.log.append(Event(type=EventType.SYSTEM, text=f"{char.name} の効果「{name}」解除", actor=char.id))
    return f"cleared {name} from {char.name}"


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


def _name(ctx: GMContext, cid: str | None) -> str:
    char = ctx.state.characters.get(cid) if cid else None
    return char.name if char else (cid or "—")


def _alive(ctx: GMContext, cid: str | None) -> bool:
    char = ctx.state.characters.get(cid) if cid else None
    return char is not None and char.hp > 0


def _begin_turn_order(ctx: GMContext, order: list[str], desc: str) -> str:
    to = ctx.state.turn_order
    to.order = list(order)
    to.round = 1
    to.index = 0
    # If the first listed combatant is already down, move to a living one.
    if to.order and not _alive(ctx, to.active):
        for _ in range(len(to.order)):
            if _alive(ctx, to.advance()):
                break
    names = " → ".join(_name(ctx, c) for c in to.order)
    ctx.log.append(
        Event(type=EventType.TURN, text=f"{desc} 行動順: {names}", data=to.to_dict())
    )
    return f"initiative set ({desc}); active: {_name(ctx, to.active)}"


def _roll_initiative(ctx: GMContext, ip: dict[str, Any]) -> str:
    ids = ip.get("combatant_ids") or list(ctx.state.characters.keys())
    order, desc = ctx.ruleset.roll_initiative(ctx.state, ids)
    return _begin_turn_order(ctx, order, desc)


def _set_turn_order(ctx: GMContext, ip: dict[str, Any]) -> str:
    return _begin_turn_order(ctx, list(ip["order"]), "行動順を設定")


def _advance_turn(ctx: GMContext, ip: dict[str, Any]) -> str:
    to = ctx.state.turn_order
    if not to.order:
        return "no turn order set; call roll_initiative first"
    if not any(_alive(ctx, c) for c in to.order):
        return "no living combatants remain"
    # Advance to the next living combatant, skipping the downed.
    active = to.active
    for _ in range(len(to.order) + 1):
        active = to.advance()
        if _alive(ctx, active):
            break
    ctx.log.append(
        Event(type=EventType.TURN,
              text=f"手番: {_name(ctx, active)}（ラウンド{to.round}）",
              data=to.to_dict())
    )
    return f"now acting: {_name(ctx, active)} ({active}), round {to.round}"


def _end_combat(ctx: GMContext, ip: dict[str, Any]) -> str:
    ctx.state.turn_order.order = []
    ctx.state.turn_order.round = 0
    ctx.state.turn_order.index = 0
    ctx.log.append(Event(type=EventType.TURN, text="戦闘終了", data={}))
    return "combat ended; initiative cleared"


def _rest(ctx: GMContext, ip: dict[str, Any]) -> str:
    ids = ip.get("character_ids")
    if ids:
        chars = [ctx.state.characters[c] for c in ids if c in ctx.state.characters]
    elif ip.get("all"):
        chars = list(ctx.state.characters.values())
    else:
        chars = ctx.state.player_characters()
    rested = []
    for char in chars:
        char.hp = char.max_hp
        if "max_pp" in char.sheet:
            char.sheet["pp"] = char.sheet["max_pp"]
        char.conditions = []
        char.sheet["effects"] = []
        rested.append(char.name)
    ctx.log.append(Event(
        type=EventType.SYSTEM,
        text=f"休息：{', '.join(rested) or '(対象なし)'} が全快し状態異常が解除された",
        data={"rested": rested},
    ))
    return f"rested: {', '.join(rested) or 'nobody'} (HP/PP restored, effects cleared)"


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
    "spawn_monster": _spawn_monster,
    "resolve_attack": _resolve_attack,
    "apply_effect": _apply_effect,
    "clear_effect": _clear_effect,
    "update_character": _update_character,
    "roll_initiative": _roll_initiative,
    "set_turn_order": _set_turn_order,
    "advance_turn": _advance_turn,
    "end_combat": _end_combat,
    "rest": _rest,
    "update_notes": _update_notes,
}
