import random

from sandcastlegm.core.state import GameState
from sandcastlegm.rulesets import registry
from sandcastlegm.rulesets.base import CheckRequest


def make_state_with_actor(**char_kwargs):
    rs = registry.create("sandcastle", rng=random.Random(7))
    state = GameState(ruleset_id="sandcastle")
    actor = rs.new_character("Erika", **char_kwargs)
    state.add_character(actor)
    return rs, state, actor


def test_sandcastle_is_registered():
    assert "sandcastle" in registry.available()


def test_new_character_has_six_abilities_and_hp():
    rs, _, actor = make_state_with_actor(level=2, abilities={"CON": 1})
    assert set(actor.sheet["abilities"]) == {"STR", "DEX", "CON", "PER", "WIL", "CHA"}
    # max_hp = (base_hp + CON) * level ; striker base 6, CON 1, level 2 -> 14
    assert actor.max_hp == (6 + 1) * 2
    assert actor.hp == actor.max_hp
    assert actor.sheet["bab"] == 1  # ceil(2/2)


def test_check_adds_ability_modifier():
    rs, state, actor = make_state_with_actor(abilities={"STR": 2})
    req = CheckRequest(actor_id=actor.id, ability="STR", target_number=3)
    result = rs.resolve_check(state, req)
    raw = result.roll.total
    assert result.total == raw + 2
    assert result.success  # TN 3 is trivially beaten


def test_trained_skill_adds_level():
    rs, state, actor = make_state_with_actor(level=3, skills=["体術"])
    req = CheckRequest(actor_id=actor.id, ability="STR", skill="体術", target_number=99)
    result = rs.resolve_check(state, req)
    # raw 3d6 + STR(0) + level(3)
    assert result.total == result.roll.total + 3
    assert any("体術(技能)+3" in b for b in result.breakdown)


def test_untrained_skill_adds_nothing():
    rs, state, actor = make_state_with_actor(level=3, skills=[])
    req = CheckRequest(actor_id=actor.id, ability="STR", skill="魔術", target_number=99)
    result = rs.resolve_check(state, req)
    assert result.total == result.roll.total
    assert any("技能なし" in b for b in result.breakdown)


def test_situational_modifiers():
    rs, state, actor = make_state_with_actor()
    req = CheckRequest(
        actor_id=actor.id,
        ability="DEX",
        modifiers={"高所": -2, "有利": 1},
        target_number=10,
    )
    result = rs.resolve_check(state, req)
    assert result.total == result.roll.total - 2 + 1


def test_critical_and_fumble_flags():
    rs, state, actor = make_state_with_actor()
    # Force outcomes by abusing the target number rather than the dice.
    big_success = rs.resolve_check(
        state, CheckRequest(actor_id=actor.id, ability="STR", target_number=3)
    )
    assert big_success.success and big_success.critical  # margin >= 5

    big_failure = rs.resolve_check(
        state, CheckRequest(actor_id=actor.id, ability="STR", target_number=30)
    )
    assert not big_failure.success and big_failure.fumble  # margin <= -5


def test_knowledge_text_loads_rulebook():
    rs = registry.create("sandcastle")
    text = rs.knowledge_text()
    assert "サンドキャッスル" in text
    assert len(text) > 1000


def test_state_serialises():
    _, state, _ = make_state_with_actor()
    d = state.to_dict()
    assert d["ruleset_id"] == "sandcastle"
    assert len(d["characters"]) == 1
