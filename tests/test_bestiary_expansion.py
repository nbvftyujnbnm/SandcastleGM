import random

from sandcastlegm.core.state import GameState
from sandcastlegm.rulesets import registry


def test_new_monsters_present_with_stats():
    rs = registry.create("sandcastle")
    cat = rs.monster_catalog()
    for key, name, hp in [("homunculus", "ホムンクルス", 3),
                          ("cockatrice", "コカトリス", 20),
                          ("polar_bear", "シロクマ", 68)]:
        assert cat[key] == name
        mob = rs.create_monster(key)
        assert mob.hp == hp and not mob.is_pc
        assert mob.sheet["attacks"]  # has at least one attack


def test_cockatrice_attack_is_usable_in_combat():
    rs = registry.create("sandcastle", rng=random.Random(3))
    state = GameState(ruleset_id="sandcastle")
    cocka = rs.create_monster("cockatrice")
    hero = rs.new_character("アリア", abilities={"DEX": 1})
    state.add_character(cocka)
    state.add_character(hero)
    result = rs.resolve_attack(state, cocka.id, hero.id, attack_name="噛みつき")
    assert result.att_bonus == 2 and result.dtype == "緑エネルギー"


def test_bestiary_size_grew():
    rs = registry.create("sandcastle")
    # 6 original + 3 added
    assert len(rs.monster_catalog()) >= 9
