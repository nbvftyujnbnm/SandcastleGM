"""Dice engine.

Parses and evaluates dice expressions in the usual ``XdY±Z`` notation and
returns a structured :class:`RollResult` that records every die face, so the GM
(and players) can see exactly how a number came to be.

The engine is generic, but it understands one ruleset-configurable wrinkle that
Sandcastle relies on: "derived" dice. Sandcastle has no physical d2 or d3 — a
d2 is a d6 halved-by-three and a d3 is a d6 halved-by-two, both rounded up. A
ruleset declares which die sizes are derived and the engine rolls a real d6 and
maps it, preserving the documented (non-uniform for multi-die) distribution.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

# One term of an expression, e.g. the "3d6" or the "+2" in "3d6+2".
_TERM = re.compile(
    r"(?P<sign>[+-])?\s*(?:(?P<count>\d*)d(?P<faces>\d+)|(?P<flat>\d+))",
    re.IGNORECASE,
)

# Sandcastle's derived dice: small die -> the source die it is rolled on, and a
# divisor applied to the source face (rounded up). d2 = ceil(d6/3); d3 = ceil(d6/2).
SANDCASTLE_DERIVED: dict[int, tuple[int, int]] = {2: (6, 3), 3: (6, 2)}


@dataclass(frozen=True)
class DieRoll:
    """A single die and the face it landed on."""

    faces: int
    value: int
    # For a derived die, the raw source face before mapping (e.g. the d6 behind a d2).
    raw: int | None = None


@dataclass(frozen=True)
class RollResult:
    """The outcome of evaluating a dice expression."""

    expression: str
    dice: tuple[DieRoll, ...]
    modifier: int
    total: int

    def describe(self) -> str:
        """Human-readable breakdown, e.g. ``3d6+2: [4, 1, 5] +2 = 12``."""
        groups: dict[int, list[int]] = {}
        for d in self.dice:
            groups.setdefault(d.faces, []).append(d.value)
        parts = [f"d{faces}{vals}" for faces, vals in sorted(groups.items())]
        body = " ".join(parts) if parts else "(no dice)"
        if self.modifier:
            body += f" {self.modifier:+d}"
        return f"{self.expression}: {body} = {self.total}"


class DiceRoller:
    """Rolls dice expressions.

    Pass a seeded :class:`random.Random` for deterministic, testable rolls.
    ``derived`` maps a die size to ``(source_faces, divisor)``; absent entries
    are rolled as ordinary uniform dice.
    """

    def __init__(
        self,
        rng: random.Random | None = None,
        derived: dict[int, tuple[int, int]] | None = None,
    ) -> None:
        self._rng = rng or random.Random()
        self._derived = derived or {}

    def _roll_one(self, faces: int) -> DieRoll:
        if faces < 1:
            raise ValueError(f"die must have >= 1 face, got d{faces}")
        if faces in self._derived:
            source, divisor = self._derived[faces]
            raw = self._rng.randint(1, source)
            value = -(-raw // divisor)  # ceil division
            return DieRoll(faces=faces, value=value, raw=raw)
        return DieRoll(faces=faces, value=self._rng.randint(1, faces))

    def roll(self, expression: str) -> RollResult:
        """Evaluate an expression such as ``"3d6"``, ``"2d6+1"`` or ``"2d3-2"``."""
        cleaned = expression.replace(" ", "")
        if not cleaned:
            raise ValueError("empty dice expression")

        dice: list[DieRoll] = []
        modifier = 0
        consumed = 0
        for m in _TERM.finditer(cleaned):
            consumed += len(m.group(0))
            sign = -1 if m.group("sign") == "-" else 1
            if m.group("flat") is not None:
                modifier += sign * int(m.group("flat"))
                continue
            count = int(m.group("count")) if m.group("count") else 1
            faces = int(m.group("faces"))
            if sign < 0:
                raise ValueError(f"cannot subtract dice in {expression!r}")
            for _ in range(count):
                dice.append(self._roll_one(faces))

        if consumed != len(cleaned):
            raise ValueError(f"could not parse dice expression {expression!r}")

        total = sum(d.value for d in dice) + modifier
        return RollResult(
            expression=expression,
            dice=tuple(dice),
            modifier=modifier,
            total=total,
        )


def sandcastle_roller(rng: random.Random | None = None) -> DiceRoller:
    """A roller configured with Sandcastle's derived d2/d3."""
    return DiceRoller(rng=rng, derived=SANDCASTLE_DERIVED)
