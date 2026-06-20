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

# A small bestiary transcribed from the rulebook's monster section. Each entry:
# level, defense, hp, pp, move, the six ability modifiers, resistance values per
# energy pair, an optional vulnerability colour, and attack actions
# (att bonus, reach, damage expression, damage type). Use these via
# spawn_monster; for anything not listed, spawn_npc makes a generic creature.
MONSTERS: dict[str, dict] = {
    "salamander": {
        "name": "サラマンダー",
        "level": 1, "defense": 18, "hp": 12, "pp": 4, "move": "10 m",
        "abilities": {"STR": 0, "DEX": -1, "CON": 1, "PER": -1, "WIL": -1, "CHA": -3},
        "resist": {"赤青": 0, "緑黄": 2, "橙紫": 0, "ヘックス": -1},
        "vulnerability": "青", "immune": "赤",
        "attacks": [
            {"name": "噛みつき", "action": "主/割", "att": 1, "reach": "近接", "damage": "1d6+1", "dtype": "通常"},
        ],
        "note": "炎・溶岩のダメージ無効。エネルギー奔出（赤）を使う。",
    },
    "monster_scorpion": {
        "name": "怪物サソリ",
        "level": 2, "defense": 17, "hp": 25, "pp": 3, "move": "8 m",
        "abilities": {"STR": 4, "DEX": 2, "CON": 2, "PER": 2, "WIL": -2, "CHA": -4},
        "resist": {"赤青": 3, "緑黄": 3, "橙紫": -1, "ヘックス": -1},
        "attacks": [
            {"name": "2爪", "action": "主/割", "att": 6, "reach": "近接", "damage": "1d6+4", "dtype": "通常"},
            {"name": "毒針", "action": "主", "att": 6, "reach": "近接", "damage": "1d6+4", "dtype": "緑エネルギー"},
        ],
        "note": "複数回攻撃：1度の攻撃行動で2回の爪、または1回の毒針。",
    },
    "brown_bear": {
        "name": "ヒグマ",
        "level": 2, "defense": 13, "hp": 43, "pp": 3, "move": "12 m",
        "abilities": {"STR": 4, "DEX": 0, "CON": 3, "PER": 1, "WIL": -2, "CHA": 0},
        "resist": {"赤青": 3, "緑黄": 4, "橙紫": 0, "ヘックス": 0},
        "attacks": [
            {"name": "2つの爪", "action": "主/割", "att": 8, "reach": "近接", "damage": "2d6+6", "dtype": "通常"},
        ],
        "note": "複数回攻撃：1度の攻撃行動で2回の爪。",
    },
    "hunting_spider": {
        "name": "狩猟蜘蛛",
        "level": 3, "defense": 16, "hp": 27, "pp": 4, "move": "14 m",
        "abilities": {"STR": 2, "DEX": 3, "CON": 1, "PER": 3, "WIL": -2, "CHA": -4},
        "resist": {"赤青": 3, "緑黄": 4, "橙紫": 1, "ヘックス": 1},
        "attacks": [
            {"name": "毒の噛みつき", "action": "主/割", "att": 5, "reach": "近接", "damage": "1d6+2", "dtype": "緑エネルギー"},
        ],
    },
    "homunculus": {
        "name": "ホムンクルス",
        "level": 0, "defense": 13, "hp": 3, "pp": 3, "move": "8 m",
        "abilities": {"STR": -3, "DEX": 2, "CON": -2, "PER": 1, "WIL": 0, "CHA": 0},
        "resist": {"赤青": 1, "緑黄": 1, "橙紫": 1, "ヘックス": -1},
        "vulnerability": "橙", "immune": "紫",
        "attacks": [
            {"name": "爪", "action": "主/割", "att": -1, "reach": "近接", "damage": "1", "dtype": "通常"},
        ],
        "note": "低レベルの使い魔。エネルギー鎧（紫）を使う。",
    },
    "cockatrice": {
        "name": "コカトリス",
        "level": 2, "defense": 14, "hp": 20, "pp": 6, "move": "10 m",
        "abilities": {"STR": 0, "DEX": 1, "CON": 1, "PER": 2, "WIL": 3, "CHA": 3},
        "resist": {"赤青": 3, "緑黄": 3, "橙紫": 4, "ヘックス": 4},
        "vulnerability": "黄",
        "attacks": [
            {"name": "噛みつき", "action": "主/割", "att": 2, "reach": "近接", "damage": "1d6", "dtype": "緑エネルギー"},
            {"name": "2爪", "action": "主/割", "att": 1, "reach": "近接", "damage": "1d3+1", "dtype": "通常"},
        ],
        "note": "緑に耐性。技能 魔術+2。石化の睨みを持つ。",
    },
    "polar_bear": {
        "name": "シロクマ",
        "level": 4, "defense": 15, "hp": 68, "pp": 5, "move": "14 m",
        "abilities": {"STR": 6, "DEX": 1, "CON": 3, "PER": 1, "WIL": 0, "CHA": 3},
        "resist": {"赤青": 3, "緑黄": 5, "橙紫": 2, "ヘックス": 2},
        "attacks": [
            {"name": "2つの爪", "action": "主/割", "att": 8, "reach": "近接", "damage": "2d6+6", "dtype": "通常"},
        ],
        "note": "大型（2マス）。複数回攻撃：1度の攻撃行動で2回の爪。",
    },
    "chimera": {
        "name": "キマイラ",
        "level": 4, "defense": 16, "hp": 50, "pp": 8, "move": "14 m",
        "abilities": {"STR": 5, "DEX": 3, "CON": 4, "PER": 4, "WIL": 0, "CHA": 5},
        "resist": {"赤青": 5, "緑黄": 5, "橙紫": 4, "ヘックス": 4},
        "attacks": [
            {"name": "噛みつき", "action": "主/割", "att": 8, "reach": "近接", "damage": "2d6+5", "dtype": "通常"},
            {"name": "炎のブレス", "action": "主", "att": 8, "reach": "遠隔", "damage": "2d6", "dtype": "赤エネルギー"},
        ],
        "note": "複数の頭が独立して行動でき、1ターンに複数の攻撃が可能。",
    },
    "demon": {
        "name": "悪魔",
        "level": 6, "defense": 18, "hp": 80, "pp": 13, "move": "10 m（歩行）/ 20 m（飛翔）",
        "abilities": {"STR": 6, "DEX": 6, "CON": 7, "PER": 7, "WIL": 8, "CHA": 8},
        "resist": {"赤青": 9, "緑黄": 10, "橙紫": 11, "ヘックス": 11},
        "vulnerability": "橙",
        "attacks": [
            {"name": "素手", "action": "主/割", "att": 9, "reach": "近接", "damage": "1d3+3", "dtype": "通常"},
            {"name": "炎の剣", "action": "主/割", "att": 12, "reach": "近接", "damage": "2d6+6", "dtype": "赤エネルギー"},
        ],
        "note": "紫・赤エネルギーを操る。飛翔可能。強敵（ボス級）。",
    },
}

# Armor (防具) table. ``bonus`` adds to defense; ``dex_penalty`` is the heavy-armor
# penalty to DEX-based defense (and 赤青 resistance) — chainmail's 敏−1. A shield
# adds a separate flat bonus.
ARMOR: dict[str, dict] = {
    "なし": {"bonus": 0, "dex_penalty": 0, "mass": 0.0},
    "革鎧": {"bonus": 1, "dex_penalty": 0, "mass": 4.5},
    "小札鎧": {"bonus": 2, "dex_penalty": 0, "mass": 20.0},
    "鎖帷子": {"bonus": 3, "dex_penalty": -1, "mass": 25.0},
}
SHIELD_BONUS = 1

# Hexes / status effects with their default modifiers. ``check`` applies to ability
# checks the afflicted makes, ``attack`` to its attack rolls, ``defense`` to its
# defense. Magnitudes are a reasonable default; the GM can override per cast.
HEXES: dict[str, dict[str, int]] = {
    "攻撃弱体ヘックス": {"attack": -2},
    "防御弱体ヘックス": {"defense": -2},
    "妨害ヘックス": {"check": -2},
    "祝福": {"check": 2},
    "守りの祝福": {"defense": 2},
}

# Energy damage colours and the ability that resists each pair.
ENERGY_RESISTANCE: dict[str, str] = {
    "赤青": "DEX",  # fire / cold
    "緑黄": "CON",  # poison / electric
    "橙紫": "WIL",  # holy / evil
    "ヘックス": "WIL",
}
