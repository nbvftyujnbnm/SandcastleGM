import random

from sandcastlegm.core.state import GameState, Scene
from sandcastlegm.core.events import EventLog
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry


def setup():
    rs = registry.create("sandcastle", rng=random.Random(3))
    state = GameState(ruleset_id="sandcastle")
    ctx = GMContext(ruleset=rs, state=state, log=EventLog())
    state.add_scene(Scene(title="場"))
    execute_tool(ctx, "create_map", {"name": "野", "width": 30, "height": 8, "cell_size_m": 2})
    return rs, state, ctx


def place(ctx, state, ch, x, y):
    state.add_character(ch)
    execute_tool(ctx, "place_token", {"name": ch.name, "x": x, "y": y,
                                      "kind": "pc" if ch.is_pc else "enemy",
                                      "character_id": ch.id})
    return ch


def test_weapon_catalog_has_ranged_data():
    rs = registry.create("sandcastle", rng=random.Random(0))
    cat = rs.weapon_catalog()
    assert cat["弓"]["reach"] == "遠隔" and cat["弓"]["range_m"] == 30
    assert cat["剣"]["reach"] == "近接" and "range_m" not in cat["剣"]


def test_new_character_weapons_become_attacks():
    rs = registry.create("sandcastle", rng=random.Random(0))
    pc = rs.new_character("アリア", level=2, abilities={"STR": 1, "PER": 2},
                          weapons=["剣", "弓"])
    attacks = {a["name"]: a for a in pc.sheet["attacks"]}
    # bab = ceil(2/2) = 1; melee att = bab+STR, ranged att = bab+PER.
    assert attacks["剣"]["att"] == 2 and attacks["剣"]["damage"] == "1d6+1"
    assert attacks["弓"]["att"] == 3 and attacks["弓"]["range_m"] == 30
    assert attacks["弓"]["reach"] == "遠隔"


def test_bow_range_comes_from_sheet_data():
    rs, state, ctx = setup()
    archer = place(ctx, state, rs.new_character("射手", weapons=["弓"]), 0, 0)
    target = place(ctx, state, rs.new_character("的", is_pc=False), 14, 0)  # 28 m
    out = execute_tool(ctx, "resolve_attack", {
        "attacker_id": archer.id, "target_id": target.id, "attack_name": "弓"})
    assert "範囲外" not in out  # 28 m <= 30 m: resolves

    far = place(ctx, state, rs.new_character("彼方の的", is_pc=False), 16, 0)  # 32 m
    out = execute_tool(ctx, "resolve_attack", {
        "attacker_id": archer.id, "target_id": far.id, "attack_name": "弓"})
    assert "範囲外" in out and "30" in out  # the weapon's own range in the message


def test_catalog_fallback_without_sheet_attack():
    # A character with no attacks on the sheet still gets the catalog's range
    # (and damage dice) when naming a catalog weapon directly.
    rs, state, ctx = setup()
    pc = place(ctx, state, rs.new_character("ならず者"), 0, 0)
    far = place(ctx, state, rs.new_character("的", is_pc=False), 6, 0)  # 12 m
    out = execute_tool(ctx, "resolve_attack", {
        "attacker_id": pc.id, "target_id": far.id, "attack_name": "投げナイフ"})
    assert "範囲外" in out and "10" in out  # 12 m > the knife's 10 m


def test_explicit_range_arg_still_wins():
    rs, state, ctx = setup()
    archer = place(ctx, state, rs.new_character("射手", weapons=["弓"]), 0, 0)
    target = place(ctx, state, rs.new_character("的", is_pc=False), 14, 0)  # 28 m
    out = execute_tool(ctx, "resolve_attack", {
        "attacker_id": archer.id, "target_id": target.id, "attack_name": "弓",
        "range_m": 20})
    assert "範囲外" in out  # explicit 20 m override beats the weapon's 30 m


def test_chimera_breath_has_data_range():
    rs, state, ctx = setup()
    chimera = place(ctx, state, rs.create_monster("chimera"), 0, 0)
    prey = place(ctx, state, rs.new_character("獲物"), 12, 0)  # 24 m > 20 m
    out = execute_tool(ctx, "resolve_attack", {
        "attacker_id": chimera.id, "target_id": prey.id, "attack_name": "炎のブレス"})
    assert "範囲外" in out and "20" in out
