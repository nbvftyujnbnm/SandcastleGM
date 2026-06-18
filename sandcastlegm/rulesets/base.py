"""The ruleset ("patch") interface.

A *ruleset* is the seam that makes the GM system game-agnostic. The engine, the
map, the AI orchestration, and the VTT adapters all talk to this interface and
never hard-code Sandcastle's mechanics. Supporting a new open-source system is
"writing a patch": subclass :class:`Ruleset`, implement the handful of methods
below, register it, and the same AI GM now runs that game.

A ruleset owns three things:

1. **Mechanics** — how dice resolve a check (``resolve_check``), and what a
   blank character looks like (``new_character`` / ``ability_definitions``).
2. **Knowledge** — the rules text the AI GM reads to adjudicate fairly
   (``knowledge_text``).
3. **Voice** — system-prompt guidance describing tone, structure, and the
   ruleset's idioms (``gm_guidance``).
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sandcastlegm.core.dice import DiceRoller, RollResult
from sandcastlegm.core.state import Character


@dataclass
class AbilityDef:
    """One ability/attribute the ruleset's characters have."""

    key: str          # short code, e.g. "STR"
    name: str         # display name, e.g. "Strength" / "筋力"
    abbreviation: str = ""  # one-character form used on sheets, e.g. "筋"
    description: str = ""


@dataclass
class CheckRequest:
    """A request to resolve an action under the ruleset's core mechanic."""

    actor_id: str | None = None
    ability: str | None = None     # ability key being tested
    skill: str | None = None       # skill applied, if any
    target_number: int | None = None  # difficulty (None = ruleset default)
    modifiers: dict[str, int] = field(default_factory=dict)  # label -> value
    description: str = ""           # what the actor is attempting


@dataclass
class CheckResult:
    """The structured outcome of a resolved check."""

    request: CheckRequest
    roll: RollResult
    total: int
    target_number: int
    success: bool
    margin: int                      # total - target_number
    critical: bool = False           # exceptional success
    fumble: bool = False             # exceptional failure
    breakdown: list[str] = field(default_factory=list)  # human-readable terms

    def describe(self) -> str:
        verdict = "SUCCESS" if self.success else "FAILURE"
        if self.critical:
            verdict = "CRITICAL SUCCESS"
        elif self.fumble:
            verdict = "FUMBLE"
        terms = " ".join(self.breakdown)
        return (
            f"{self.roll.describe()}  ({terms})  "
            f"vs TN {self.target_number} -> {verdict} (margin {self.margin:+d})"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "ability": self.request.ability,
            "skill": self.request.skill,
            "description": self.request.description,
            "roll": self.roll.describe(),
            "total": self.total,
            "target_number": self.target_number,
            "success": self.success,
            "margin": self.margin,
            "critical": self.critical,
            "fumble": self.fumble,
            "breakdown": list(self.breakdown),
        }


@dataclass
class AttackResult:
    """The outcome of resolving an attack (to-hit, and damage if it lands)."""

    attacker_id: str | None
    target_id: str
    attack_name: str | None
    att_bonus: int
    attack_roll: RollResult
    att_total: int
    defense: int
    hit: bool
    damage_expr: str | None = None
    damage_roll: RollResult | None = None
    damage: int = 0
    dtype: str | None = None

    def describe(self) -> str:
        head = (
            f"{self.attack_name or 'attack'}: {self.attack_roll.describe()} "
            f"+att{self.att_bonus:+d} = {self.att_total} vs 防御{self.defense} -> "
            + ("命中" if self.hit else "外れ")
        )
        if self.hit and self.damage_roll is not None:
            head += f" / ダメージ {self.damage_roll.describe()} = {self.damage}"
            if self.dtype:
                head += f"（{self.dtype}）"
        return head

    def to_dict(self) -> dict[str, Any]:
        return {
            "attacker_id": self.attacker_id,
            "target_id": self.target_id,
            "attack_name": self.attack_name,
            "att_bonus": self.att_bonus,
            "att_total": self.att_total,
            "defense": self.defense,
            "hit": self.hit,
            "damage": self.damage,
            "dtype": self.dtype,
            "attack_roll": self.attack_roll.describe(),
            "damage_roll": self.damage_roll.describe() if self.damage_roll else None,
        }


class Ruleset(ABC):
    """Base class for a playable system. Subclass it to add a new game."""

    #: stable identifier used to select the ruleset (e.g. "sandcastle")
    id: str = "base"
    #: display name
    name: str = "Base Ruleset"
    #: short description shown when listing available systems
    description: str = ""
    #: default difficulty when the GM does not specify one
    default_target_number: int = 11

    def __init__(self, rng: random.Random | None = None) -> None:
        self._roller = self.make_roller(rng)

    # --- mechanics ------------------------------------------------------------
    def make_roller(self, rng: random.Random | None) -> DiceRoller:
        """Return the dice roller this system uses. Override for derived dice."""
        return DiceRoller(rng=rng)

    @property
    def roller(self) -> DiceRoller:
        return self._roller

    @abstractmethod
    def ability_definitions(self) -> list[AbilityDef]:
        """The abilities every character of this system has."""

    @abstractmethod
    def new_character(self, name: str, **kwargs: Any) -> Character:
        """Create a blank, valid character for this system."""

    @abstractmethod
    def resolve_check(self, state: Any, request: CheckRequest) -> CheckResult:
        """Resolve an action using the system's core mechanic.

        ``state`` is the :class:`~sandcastlegm.core.state.GameState`, passed so
        the ruleset can read the acting character's sheet for ability values,
        skill bonuses, level, and so on.
        """

    def roll_initiative(self, state: Any, combatant_ids: list[str]) -> tuple[list[str], str]:
        """Decide turn order for a fight.

        Default (and Sandcastle's rule): the player side and the opposing side
        each roll one die; the higher roll acts first, ties favour the PCs. Order
        within a side is preserved as given. Returns ``(ordered_ids, description)``.
        """
        chars = getattr(state, "characters", {})
        pcs = [c for c in combatant_ids if getattr(chars.get(c), "is_pc", False)]
        foes = [c for c in combatant_ids if c not in pcs]
        pc_roll = self.roller.roll("1d6").total if pcs else -1
        foe_roll = self.roller.roll("1d6").total if foes else -1
        pcs_first = pc_roll >= foe_roll  # ties favour the PCs
        order = (pcs + foes) if pcs_first else (foes + pcs)
        desc = (
            f"先攻判定: PC側 1d6={pc_roll if pcs else '—'} / 敵側 1d6={foe_roll if foes else '—'}"
            f" → {'PC' if pcs_first else '敵'}側が先攻"
        )
        return order, desc

    def resolve_attack(
        self,
        state: Any,
        attacker_id: str | None,
        target_id: str,
        *,
        att: int | None = None,
        damage: str | None = None,
        attack_name: str | None = None,
        modifier: int = 0,
    ) -> AttackResult:
        """Resolve an attack: roll 3d6 + attack bonus against the target's defense,
        and roll damage on a hit. Does not mutate state (the caller applies HP).

        Resolution order for the attack bonus and damage:
        the explicit ``att``/``damage`` args, else a matching named attack on the
        attacker's monster sheet, else the attacker's ``bab`` and ``1d6``.
        Defense uses the target's sheet ``defense``, else ``10 + DEX``.
        """
        chars = getattr(state, "characters", {})
        attacker = chars.get(attacker_id) if attacker_id else None
        target = chars.get(target_id)
        if target is None:
            raise ValueError(f"unknown target {target_id!r}")

        a_sheet = attacker.sheet if attacker else {}
        if (att is None or damage is None) and attack_name:
            for atk in a_sheet.get("attacks", []):
                if atk.get("name") == attack_name:
                    att = atk.get("att") if att is None else att
                    damage = damage or atk.get("damage")
                    break
        dtype = None
        for atk in a_sheet.get("attacks", []):
            if atk.get("name") == attack_name:
                dtype = atk.get("dtype")
        if att is None:
            att = int(a_sheet.get("bab", 0))
        damage_expr = damage or "1d6"

        t_sheet = target.sheet
        defense = t_sheet.get("defense")
        if defense is None:
            defense = 10 + int(t_sheet.get("abilities", {}).get("DEX", 0))
        defense = int(defense)

        roll = self.roller.roll("3d6")
        att_total = roll.total + int(att) + int(modifier)
        hit = att_total >= defense

        dmg_roll = self.roller.roll(damage_expr) if hit else None
        return AttackResult(
            attacker_id=attacker_id,
            target_id=target_id,
            attack_name=attack_name,
            att_bonus=int(att) + int(modifier),
            attack_roll=roll,
            att_total=att_total,
            defense=defense,
            hit=hit,
            damage_expr=damage_expr if hit else None,
            damage_roll=dmg_roll,
            damage=dmg_roll.total if dmg_roll else 0,
            dtype=dtype,
        )

    # --- bestiary (optional; systems without one inherit the empty default) ---
    def monster_catalog(self) -> dict[str, str]:
        """Map of ``monster_key -> display name`` the GM can spawn. Empty by default."""
        return {}

    def create_monster(self, key: str, name: str | None = None) -> Character:
        """Create a statted monster from the bestiary. Raises ``KeyError`` if absent."""
        raise KeyError(key)

    # --- knowledge & voice ----------------------------------------------------
    @abstractmethod
    def knowledge_text(self) -> str:
        """The rules corpus the AI GM reads to adjudicate the game."""

    def gm_guidance(self) -> str:
        """System-specific guidance appended to the GM system prompt."""
        return ""
