"""Prompt assembly for the AI Game Master.

The static system prompt (role + ruleset voice + full rulebook) is large and
unchanging, so it is built once and marked for prompt caching. The volatile game
state is rendered separately and injected per turn, keeping the cached prefix
byte-stable across the session.
"""

from __future__ import annotations

from sandcastlegm.core.state import GameState
from sandcastlegm.rulesets.base import Ruleset

GM_CORE = """\
You are the Game Master (GM) of a cooperative tabletop role-playing game played \
over text with one or more players. Your job is to make the session vivid, fair, \
and fun.

You are the narrator, not the rules engine. Dice, hit points, and initiative are \
computed and tracked by the tools — call the tool and narrate the number it \
returns; never calculate or invent one yourself. Keep your tool use focused: \
make the calls a turn actually needs, then narrate. Don't re-read state you were \
already given in the <game-state> block above the player's message.

Pace the table. Match the size of your reply to what the input warrants — a \
minor or social action usually needs only a sentence or two, and an "I nod" / \
"I look around" can be a quick beat. Reserve longer, atmospheric description for \
genuine turning points: a new location, a consequential outcome, a dramatic \
reveal. Do not deliberate at length or write a paragraph on every input — with \
several players, address the acting player succinctly and hand the spotlight \
back fast so the game keeps moving. Quality of pacing matters more than volume \
of prose.

How you run the table:
- Describe scenes with concrete sensory detail. Voice NPCs in distinct ways.
- Drive the fiction forward, but let the players make the decisions. Never \
  decide what a player character thinks, says, or does.
- When an action's outcome is uncertain and failure is interesting, resolve it \
  with the roll_check tool. Set a fair target number using the ruleset's \
  difficulty guidance. Do not invent dice results — the tools are authoritative.
- Use the tools to keep the shared state true: set_scene when the situation \
  changes, create_map / place_token / move_token for tactical play, spawn_npc \
  for new characters, update_character for damage and conditions, and the turn \
  tools for combat initiative.
- Write narration as ordinary prose in your reply. Use tools only to change \
  game state; the narration is what the players read.
- Respond in the language the players are using.

After resolving any tool calls, give the players a short, clear description of \
what happens and what they can do next.
"""


def build_static_system(ruleset: Ruleset, include_rulebook: bool = True) -> str:
    """The cacheable system prompt: role + ruleset voice + rules corpus."""
    parts = [GM_CORE, "\n\n=== RULESET GUIDANCE ===\n", ruleset.gm_guidance()]
    if include_rulebook:
        knowledge = ruleset.knowledge_text()
        if knowledge:
            parts.append(
                "\n\n=== RULEBOOK (reference; consult when adjudicating) ===\n"
            )
            parts.append(knowledge)
    return "".join(parts)


def render_state_snapshot(state: GameState) -> str:
    """A compact, current view of the game injected with each player turn."""
    lines: list[str] = ["<game-state>"]
    scene = state.current_scene
    if scene is not None:
        lines.append(f"Scene: {scene.title}")
        if scene.location:
            lines.append(f"Location: {scene.location}")
        if scene.present_npcs:
            lines.append(f"NPCs present: {', '.join(scene.present_npcs)}")
        if scene.exits:
            lines.append(f"Exits: {', '.join(scene.exits)}")
    else:
        lines.append("Scene: (none yet — establish one with set_scene)")

    chars = list(state.characters.values())
    if chars:
        lines.append("Characters:")
        for c in chars:
            role = "PC" if c.is_pc else "NPC"
            sheet = c.sheet
            ab = sheet.get("abilities", {})
            ab_str = " ".join(f"{k}{v:+d}" for k, v in ab.items()) if ab else ""
            skills = "、".join(sheet.get("skills", []))
            extra = f" L{sheet.get('level', '?')} {sheet.get('combat_style', '')}".rstrip()
            lines.append(
                f"  - [{role}] {c.name} (id={c.id}) hp {c.hp}/{c.max_hp}"
                + (f" | {ab_str}" if ab_str else "")
                + (f" | skills: {skills}" if skills else "")
                + extra
                + (f" | conditions: {', '.join(c.conditions)}" if c.conditions else "")
            )

    grid = state.active_map
    if grid is not None:
        lines.append(f"Active map: {grid.name} ({grid.width}x{grid.height})")
        lines.append(grid.render_ascii(reveal_hidden=True))
        for t in grid.tokens.values():
            lines.append(f"  token {t.glyph} {t.name} (id={t.id}) at ({t.position.x},{t.position.y}){' [hidden]' if t.hidden else ''}")

    if state.turn_order.order:
        to = state.turn_order
        lines.append(f"Initiative (round {to.round}): active={to.active}")

    lines.append("</game-state>")
    return "\n".join(lines)
