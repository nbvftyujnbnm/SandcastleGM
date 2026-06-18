import json
import random

from sandcastlegm.core.events import EventLog, EventType
from sandcastlegm.core.state import GameState
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry


def setup():
    rs = registry.create("sandcastle", rng=random.Random(4))
    state = GameState(ruleset_id="sandcastle")
    ctx = GMContext(ruleset=rs, state=state, log=EventLog())
    hero = rs.new_character("アリア", level=2, abilities={"DEX": 2})
    state.add_character(hero)
    return rs, state, ctx, hero


def test_guaranteed_hit_applies_damage():
    rs, state, ctx, hero = setup()
    bear = rs.create_monster("brown_bear")
    state.add_character(bear)
    before = hero.hp
    out = json.loads(execute_tool(ctx, "resolve_attack", {
        "attacker_id": bear.id, "target_id": hero.id, "att": 100, "damage": "1d6+2"}))
    assert out["hit"] is True
    assert out["damage"] >= 3
    assert hero.hp == max(0, before - out["damage"])
    assert any(e.type == EventType.ROLL for e in ctx.log.events)


def test_guaranteed_miss_deals_no_damage():
    rs, state, ctx, hero = setup()
    before = hero.hp
    out = json.loads(execute_tool(ctx, "resolve_attack", {
        "target_id": hero.id, "att": -100, "damage": "2d6"}))
    assert out["hit"] is False
    assert out["damage"] == 0
    assert hero.hp == before


def test_named_attack_uses_sheet_stats():
    rs, state, ctx, hero = setup()
    demon = rs.create_monster("demon")
    state.add_character(demon)
    # The demon's 炎の剣 is att +12 / 2d6+6 / 赤エネルギー; force the target to be hittable.
    result = rs.resolve_attack(state, demon.id, hero.id, attack_name="炎の剣")
    assert result.att_bonus == 12
    assert result.dtype == "赤エネルギー"
    if result.hit:
        assert result.damage >= 8  # 2d6+6 minimum


def test_downing_target_adds_condition():
    rs, state, ctx, hero = setup()
    hero.hp = 3
    execute_tool(ctx, "resolve_attack", {"target_id": hero.id, "att": 100, "damage": "2d6+10"})
    assert hero.hp == 0
    assert "戦闘不能" in hero.conditions


def test_defense_falls_back_to_ten_plus_dex():
    rs, state, ctx, hero = setup()  # hero DEX +2 -> defense 12, no armor set
    # att total = 3d6 + att; with att = 9, min 3d6=3 -> 12 >= 12 always hits.
    result = rs.resolve_attack(state, None, hero.id, att=9, damage="1d6")
    assert result.defense == 12
    assert result.hit is True


def test_monster_vs_monster_targets_defense_stat():
    rs, state, ctx, hero = setup()
    bear = rs.create_monster("brown_bear")   # defense 13
    demon = rs.create_monster("demon")
    state.add_character(bear)
    state.add_character(demon)
    result = rs.resolve_attack(state, demon.id, bear.id, attack_name="炎の剣")
    assert result.defense == 13  # bear's sheet defense, not the DEX fallback
