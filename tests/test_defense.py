import random

from sandcastlegm.rulesets import registry


def rs():
    return registry.create("sandcastle", rng=random.Random(1))


def test_unarmored_defense_is_ten_plus_dex():
    r = rs()
    pc = r.new_character("アリア", abilities={"DEX": 2})
    assert pc.sheet["defense"] == 12  # 10 + DEX 2 + db 0 + armor 0
    assert pc.sheet["armor"] == "なし"


def test_leather_and_shield_add_bonuses():
    r = rs()
    pc = r.new_character("ボロミ", abilities={"DEX": 1}, armor="革鎧", shield=True)
    # 10 + DEX 1 + db 0 + armor 1 + shield 1 = 13
    assert pc.sheet["defense"] == 13
    assert pc.sheet["armor"] == "革鎧" and pc.sheet["shield"] is True


def test_chainmail_net_plus_two_from_dex_penalty():
    r = rs()
    pc = r.new_character("騎士", abilities={"DEX": 0}, armor="鎖帷子")
    # 10 + 0 + db 0 + armor 3 + shield 0 + dex_penalty -1 = 12
    assert pc.sheet["defense"] == 12


def test_harrier_gets_defense_bonus_from_level():
    r = rs()
    pc = r.new_character("斥候", level=4, abilities={"DEX": 1}, combat_style="ハリアー")
    # db = ceil(4/2) = 2 ; 10 + 1 + 2 = 13
    assert pc.sheet["db"] == 2
    assert pc.sheet["defense"] == 13


def test_resolve_attack_uses_computed_pc_defense():
    from sandcastlegm.core.state import GameState

    r = rs()
    state = GameState(ruleset_id="sandcastle")
    pc = r.new_character("アリア", abilities={"DEX": 2}, armor="鎖帷子")  # defense 14
    state.add_character(pc)
    result = r.resolve_attack(state, None, pc.id, att=0, damage="1d6")
    assert result.defense == pc.sheet["defense"] == 14  # not the 10+DEX fallback (12)
