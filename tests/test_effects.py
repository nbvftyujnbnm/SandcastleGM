import random

from sandcastlegm.core.events import EventLog
from sandcastlegm.core.state import GameState
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry
from sandcastlegm.rulesets.base import CheckRequest


def setup():
    rs = registry.create("sandcastle", rng=random.Random(6))
    state = GameState(ruleset_id="sandcastle")
    ctx = GMContext(ruleset=rs, state=state, log=EventLog())
    hero = rs.new_character("アリア", level=2, abilities={"STR": 1})
    state.add_character(hero)
    return rs, state, ctx, hero


def test_apply_hex_from_catalog():
    rs, state, ctx, hero = setup()
    out = execute_tool(ctx, "apply_effect", {"character_id": hero.id, "hex": "攻撃弱体ヘックス"})
    assert "攻撃弱体ヘックス" in out
    eff = hero.sheet["effects"][0]
    assert eff["name"] == "攻撃弱体ヘックス" and eff["mods"]["attack"] == -2
    assert "攻撃弱体ヘックス" in hero.conditions


def test_check_modifier_applied_and_cleared():
    rs, state, ctx, hero = setup()
    base = rs.resolve_check(state, CheckRequest(actor_id=hero.id, ability="STR", target_number=10))
    execute_tool(ctx, "apply_effect", {"character_id": hero.id, "name": "妨害", "mods": {"check": -3}})
    hexed = rs.resolve_check(state, CheckRequest(actor_id=hero.id, ability="STR", target_number=10))
    assert hexed.total == hexed.roll.total + 1 - 3  # STR +1, effect -3
    assert any("状態効果-3" in b for b in hexed.breakdown)

    execute_tool(ctx, "clear_effect", {"character_id": hero.id, "name": "妨害"})
    after = rs.resolve_check(state, CheckRequest(actor_id=hero.id, ability="STR", target_number=10))
    assert after.total == after.roll.total + 1
    assert hero.sheet["effects"] == []
    _ = base  # silence unused


def test_attack_and_defense_effects():
    rs, state, ctx, hero = setup()
    foe = rs.create_monster("brown_bear")
    state.add_character(foe)
    # Weaken the bear's attack and the hero's defense.
    execute_tool(ctx, "apply_effect", {"character_id": foe.id, "hex": "攻撃弱体ヘックス"})  # attack -2
    execute_tool(ctx, "apply_effect", {"character_id": hero.id, "hex": "防御弱体ヘックス"})  # defense -2
    result = rs.resolve_attack(state, foe.id, hero.id, att=5)
    # att_bonus includes -2 from the attacker's hex; defense reduced by 2.
    assert result.att_bonus == 5 - 2
    assert result.defense == hero.sheet["defense"] - 2


def test_apply_effect_replaces_same_name():
    rs, state, ctx, hero = setup()
    execute_tool(ctx, "apply_effect", {"character_id": hero.id, "name": "弱体", "mods": {"check": -1}})
    execute_tool(ctx, "apply_effect", {"character_id": hero.id, "name": "弱体", "mods": {"check": -4}})
    assert len(hero.sheet["effects"]) == 1
    assert hero.sheet["effects"][0]["mods"]["check"] == -4


def test_hex_catalog_exposed():
    rs = registry.create("sandcastle")
    assert "攻撃弱体ヘックス" in rs.hex_catalog()
    assert registry.create("sandcastle").hex_catalog()["祝福"]["check"] == 2
