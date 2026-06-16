"""GM narrative probe scenarios, grounded in a shared Sandcastle mini-setting.

Every model under test gets the same persona and setting, then each scenario
asks for one GM narration turn. Keeping the setting fixed isolates writing
quality from world-building luck. Each scenario tags what good output should
contain (``expects``) so the auto-scorer can apply scenario-specific checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# The shared world every scenario builds on.
SETTING = """\
System: Sandcastle TRPG. Tone: gritty low-fantasy adventure, collaborative and fun.
Place: Ashnook (灰隅), a tilted tower-town clinging to a cliff below a smouldering
ridge; soot drifts in the air and everything tastes faintly of ash. The players
are fresh adventurers chartered by the Salvage Academy guild. A recurring NPC is
Nora, a wary fence who trades in scavenged relics.
"""

PROBE_SYSTEM = (
    "You are the Game Master narrating a Sandcastle tabletop RPG session for the "
    "players. Write only in-fiction narration — vivid, sensory, and forward-moving "
    "— in one to three short paragraphs. Voice NPCs with distinct speech. Do not "
    "talk about rules, dice, or tools, and do not invent dice numbers; the table's "
    "tools handle mechanics. End in a way that invites the players to act.\n\n"
    + SETTING
)


@dataclass
class Scenario:
    key: str
    instruction: str
    expects: set[str] = field(default_factory=set)  # {"dialogue", "hook"}


SCENARIOS: list[Scenario] = [
    Scenario(
        "scene_entry",
        "Describe the party arriving at Ashnook's market tier at dusk.",
        expects=set(),
    ),
    Scenario(
        "npc_meeting",
        "Introduce Nora, the fence the party has come to meet, as she appears.",
        expects={"dialogue"},
    ),
    Scenario(
        "yes_and",
        "Mid-scene, a player kicks a glowing brazier into a pursuing guard's path. "
        "Narrate the immediate consequence.",
        expects={"hook"},
    ),
    Scenario(
        "consequence",
        "Last session the party skipped out on a debt to Nora. Open this scene with "
        "the fallout catching up to them.",
        expects={"hook"},
    ),
    Scenario(
        "pacing",
        "Mid-scene, shift the tension: the player realises they are being shadowed "
        "through the crowd.",
        expects={"hook"},
    ),
    Scenario(
        "closing_beat",
        "End the session on a hook that makes the players want to return next time.",
        expects={"hook"},
    ),
    Scenario(
        "combat_hit",
        "The rules engine has already resolved a hit: the fighter's axe lands on a "
        "goblin for solid damage. Narrate that blow vividly (do not state numbers).",
        expects=set(),
    ),
    Scenario(
        "player_failure",
        "A player just failed a climb check on a soot-slick wall. Narrate a "
        "fail-forward outcome that complicates things without dead-ending the scene.",
        expects={"hook"},
    ),
]
