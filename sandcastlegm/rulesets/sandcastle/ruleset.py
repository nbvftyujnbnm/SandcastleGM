"""The Sandcastle ruleset — the reference implementation of the patch interface.

Core mechanic (能力値判定): roll 3d6, add the relevant ability modifier, add a
bonus equal to the character's level if a trained skill applies, add any
situational modifiers the GM sets, and compare the total to the target number.
Total >= TN succeeds.
"""

from __future__ import annotations

import random
from importlib import resources
from typing import Any

from sandcastlegm.core.dice import DiceRoller, sandcastle_roller
from sandcastlegm.core.state import Character
from sandcastlegm.rulesets.base import (
    AbilityDef,
    CheckRequest,
    CheckResult,
    Ruleset,
)
from sandcastlegm.rulesets.registry import register
from sandcastlegm.rulesets.sandcastle import data

# Engine convention layered on Sandcastle (which leaves degree-of-success to GM
# narration): a check that clears or misses the TN by this much is flagged as a
# critical / fumble so the GM can colour the outcome. Purely advisory.
CRIT_MARGIN = 5
FUMBLE_MARGIN = -5


@register
class SandcastleRuleset(Ruleset):
    id = "sandcastle"
    name = "Sandcastle TRPG"
    description = (
        "A light, open-source fantasy-adventure TRPG. 3d6 + ability + skill vs a "
        "target number; six abilities, twelve skills, subspecies and combat styles."
    )
    default_target_number = data.DEFAULT_TARGET_NUMBER

    def make_roller(self, rng: random.Random | None) -> DiceRoller:
        # Sandcastle's d2/d3 are derived from a d6.
        return sandcastle_roller(rng)

    # --- mechanics ------------------------------------------------------------
    def ability_definitions(self) -> list[AbilityDef]:
        return list(data.ABILITIES)

    def new_character(self, name: str, **kwargs: Any) -> Character:
        """Create a starting Sandcastle character.

        Accepted kwargs: ``level`` (default 1), ``subspecies`` (default 人間),
        ``combat_style`` (default ストライカー), ``abilities`` (dict of modifiers),
        ``skills`` (list of trained skill names), ``controller``.
        """
        level = int(kwargs.get("level", 1))
        subspecies = kwargs.get("subspecies", "人間")
        combat_style = kwargs.get("combat_style", "ストライカー")

        abilities = {k: 0 for k in data.ABILITY_KEYS}
        abilities.update(kwargs.get("abilities", {}))

        skills = list(kwargs.get("skills", []))

        base_hp = data.COMBAT_STYLES.get(combat_style, {}).get("base_hp", 4)
        con = abilities.get("CON", 0)
        # 最大hp = (戦闘様式の基礎 + 耐久力) × レベル
        max_hp = max(1, (base_hp + con) * level)

        bab = -(-level // 2)  # 基礎攻撃ボーナス = レベルの半分（切り上げ）

        sheet = {
            "level": level,
            "subspecies": subspecies,
            "combat_style": combat_style,
            "abilities": abilities,
            "skills": skills,
            "bab": bab,
            "xp": 0,
        }
        return Character(
            name=name,
            is_pc=bool(kwargs.get("is_pc", True)),
            controller=kwargs.get("controller"),
            sheet=sheet,
            hp=max_hp,
            max_hp=max_hp,
        )

    def resolve_check(self, state: Any, request: CheckRequest) -> CheckResult:
        roll = self._roller.roll("3d6")
        breakdown = [f"3d6={roll.total - roll.modifier}"]
        total = roll.total

        sheet = self._sheet_for(state, request.actor_id)

        # Ability modifier.
        if request.ability:
            ability_mod = int(sheet.get("abilities", {}).get(request.ability, 0))
            if ability_mod:
                breakdown.append(f"{request.ability}{ability_mod:+d}")
            total += ability_mod

        # Skill bonus equals level when the character is trained in the named skill.
        if request.skill:
            level = int(sheet.get("level", 0))
            if request.skill in sheet.get("skills", []):
                breakdown.append(f"{request.skill}(技能)+{level}")
                total += level
            else:
                breakdown.append(f"{request.skill}(技能なし)+0")

        # Arbitrary situational modifiers the GM applies.
        for label, value in request.modifiers.items():
            if value:
                breakdown.append(f"{label}{value:+d}")
            total += value

        tn = request.target_number if request.target_number is not None else self.default_target_number
        margin = total - tn
        success = margin >= 0
        critical = success and margin >= CRIT_MARGIN
        fumble = (not success) and margin <= FUMBLE_MARGIN

        return CheckResult(
            request=request,
            roll=roll,
            total=total,
            target_number=tn,
            success=success,
            margin=margin,
            critical=critical,
            fumble=fumble,
            breakdown=breakdown,
        )

    # --- knowledge & voice ----------------------------------------------------
    def knowledge_text(self) -> str:
        try:
            return (
                resources.files("sandcastlegm.rulesets.sandcastle.knowledge")
                .joinpath("rulebook_ja.txt")
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError):
            return ""

    def gm_guidance(self) -> str:
        ability_lines = "\n".join(
            f"  - {a.key} {a.name}（{a.abbreviation}）: {a.description}"
            for a in data.ABILITIES
        )
        skill_list = "、".join(data.SKILL_KEYS)
        tn_lines = "\n".join(
            f"  - {label}: TN {tn}" for label, tn in data.TARGET_NUMBER_GUIDANCE.items()
        )
        return (
            "You are running Sandcastle, a light fantasy-adventure TRPG.\n"
            "Core mechanic: every uncertain action is an ability check — roll 3d6, "
            "add the relevant ability modifier, add the character's level if a "
            "trained skill applies, add situational modifiers, and compare to a "
            "target number (TN). Total >= TN succeeds. Use the roll_check tool to "
            "resolve checks; never invent dice results.\n\n"
            f"Abilities:\n{ability_lines}\n\n"
            f"Skills (a trained one adds the actor's level when relevant): {skill_list}\n\n"
            "Difficulty guidance — 3d6 lands in 8..13 two-thirds of the time:\n"
            f"{tn_lines}\n\n"
            "Tone: collaborative and fun, like cooperative make-believe. Failure "
            "should be interesting, not punishing. Describe vivid scenes, voice the "
            "NPCs, and let the players drive."
        )

    # --- helpers --------------------------------------------------------------
    @staticmethod
    def _sheet_for(state: Any, actor_id: str | None) -> dict[str, Any]:
        if actor_id and getattr(state, "characters", None):
            char = state.characters.get(actor_id)
            if char is not None:
                return char.sheet
        return {}
