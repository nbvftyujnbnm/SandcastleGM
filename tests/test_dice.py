import random

import pytest

from sandcastlegm.core.dice import DiceRoller, sandcastle_roller


def test_parse_simple():
    r = DiceRoller(random.Random(1))
    result = r.roll("3d6")
    assert len(result.dice) == 3
    assert all(1 <= d.value <= 6 for d in result.dice)
    assert result.total == sum(d.value for d in result.dice)


def test_modifiers():
    r = DiceRoller(random.Random(1))
    result = r.roll("2d6+3")
    assert result.modifier == 3
    assert result.total == sum(d.value for d in result.dice) + 3

    result = r.roll("1d6-2")
    assert result.modifier == -2


def test_implicit_count():
    r = DiceRoller(random.Random(1))
    result = r.roll("d6")
    assert len(result.dice) == 1


def test_invalid_expressions():
    r = DiceRoller(random.Random(1))
    with pytest.raises(ValueError):
        r.roll("")
    with pytest.raises(ValueError):
        r.roll("3x6")
    with pytest.raises(ValueError):
        r.roll("garbage")


def test_derived_d2_distribution():
    # d2 = ceil(d6/3): faces 1,2,3 -> 1 ; 4,5,6 -> 2
    expected = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2, 6: 2}
    for face, want in expected.items():
        roller = sandcastle_roller(random.Random())
        roller._rng = _FixedRandom(face)  # type: ignore[attr-defined]
        result = roller.roll("d2")
        assert result.dice[0].value == want
        assert result.dice[0].raw == face


def test_derived_d3_distribution():
    # d3 = ceil(d6/2): 1,2 -> 1 ; 3,4 -> 2 ; 5,6 -> 3
    expected = {1: 1, 2: 1, 3: 2, 4: 2, 5: 3, 6: 3}
    for face, want in expected.items():
        roller = sandcastle_roller(random.Random())
        roller._rng = _FixedRandom(face)  # type: ignore[attr-defined]
        result = roller.roll("d3")
        assert result.dice[0].value == want


def test_2d3_sums_two_derived_dice():
    roller = sandcastle_roller(random.Random())
    roller._rng = _FixedRandom(6)  # type: ignore[attr-defined]
    result = roller.roll("2d3")
    # both d3 from a face-6 d6 -> 3 each -> 6
    assert result.total == 6
    assert len(result.dice) == 2


def test_describe_is_readable():
    r = DiceRoller(random.Random(42))
    text = r.roll("3d6+2").describe()
    assert "3d6+2" in text and "=" in text


class _FixedRandom:
    """A stand-in RNG that always returns the same face, for distribution tests."""

    def __init__(self, value: int) -> None:
        self._value = value

    def randint(self, a: int, b: int) -> int:
        return self._value
