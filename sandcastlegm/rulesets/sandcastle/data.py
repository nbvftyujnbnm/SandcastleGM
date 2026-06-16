"""Static Sandcastle data, transcribed from the official rulebook.

Sources: the bundled Japanese rulebook (see ``knowledge/rulebook_ja.txt``),
sections 能力値判定 (ability checks), キャラクター作成 (character creation), and
危険と困難の難易度 (difficulty table).
"""

from __future__ import annotations

from sandcastlegm.rulesets.base import AbilityDef

# The six ability values. Modifiers run roughly -2 (very poor) .. +2 (very good)
# for humans; +0 is an average adventurer.
ABILITIES: list[AbilityDef] = [
    AbilityDef("STR", "筋力", "筋", "Physical, muscle-based power; lifting, melee attacks."),
    AbilityDef("DEX", "敏捷力", "敏", "Dexterity and coordination; resists red/blue energy."),
    AbilityDef("CON", "耐久力", "耐", "Stamina and toughness; sets max HP; resists green/yellow energy."),
    AbilityDef("PER", "知覚力", "知", "Awareness, intellect and memory; perception and ranged attacks."),
    AbilityDef("WIL", "意志力", "意", "Willpower; resists coercion and hexes; resists orange/purple energy."),
    AbilityDef("CHA", "体現力", "体", "Embodiment/presence; persuasion and manipulating magical force."),
]

ABILITY_KEYS: list[str] = [a.key for a in ABILITIES]

# The twelve skills. When a character is trained in a skill relevant to the
# action, they add a bonus equal to their level. Each skill pairs with whichever
# ability the attempted action calls for (the GM decides), so skills are not
# bound to a single ability.
SKILLS: dict[str, str] = {
    "威圧": "Intimidation — frightening others into compliance.",
    "隠密": "Stealth — moving and acting unnoticed.",
    "家政学": "Home economics — cooking, cleaning, mending; spotting overlooked clues.",
    "芸能": "Performance — acting, music, dance, comedy.",
    "工学": "Engineering — machines, construction, masonry, lockpicking.",
    "詐術": "Deception — lies, disguise, impersonation, sleight of hand.",
    "社会科学": "Social science — law, economics, history, culture.",
    "生命科学": "Life science — biology, medicine, anatomy, nature.",
    "体術": "Athletics — climbing, swimming, jumping, balance, acrobatics.",
    "物理科学": "Physical science — chemistry, physics, astronomy, geology, weather.",
    "魔術": "Magic lore — recognising magic and manipulating magical force.",
    "魅了": "Charm — winning others over, seduction, fast talk.",
}
SKILL_KEYS: list[str] = list(SKILLS.keys())

# Subspecies and how many starting skills each gets (humans get one extra).
SUBSPECIES: dict[str, dict] = {
    "人間": {"skills": 3, "note": "Humans: no ability modifiers, an extra skill."},
    "ドワーフ": {"skills": 2, "note": "Dwarves: sturdy; 2 skills."},
    "エルフ": {"skills": 2, "note": "Elves: graceful; 2 skills."},
    "オニ": {"skills": 2, "note": "Oni: powerful; 2 skills."},
}

# Combat styles (戦闘様式). base_hp feeds the max-HP formula below. Values here
# are starting points for the scaffold; tune against the combat-style table in
# the rulebook for a campaign.
COMBAT_STYLES: dict[str, dict] = {
    "ストライカー": {"base_hp": 6, "note": "Striker: aggressive melee; specialty attack = melee."},
    "エネルガー": {"base_hp": 5, "note": "Energer: energy attacks; specialty attack = energy."},
    "ハリアー": {"base_hp": 4, "note": "Harrier: mobile skirmisher; extra reactions and defense bonus."},
    "ヘクサー": {"base_hp": 4, "note": "Hexer: hexes and disruption; hinders enemies without direct damage."},
}

# 危険と困難の難易度 (difficulty table). 3d6 lands in 8..13 about two-thirds of
# the time, so an unmodified average action sits near the middle of this band.
DEFAULT_TARGET_NUMBER = 11
TARGET_NUMBER_GUIDANCE: dict[str, int] = {
    "trivial": 8,
    "easy": 9,
    "moderate": 11,
    "hard": 13,
    "very_hard": 15,
    "extreme": 18,
}

# Energy damage colours and the ability that resists each pair.
ENERGY_RESISTANCE: dict[str, str] = {
    "赤青": "DEX",  # fire / cold
    "緑黄": "CON",  # poison / electric
    "橙紫": "WIL",  # holy / evil
    "ヘックス": "WIL",
}
