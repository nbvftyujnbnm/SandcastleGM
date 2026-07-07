import random

from sandcastlegm.core.events import EventLog, EventType
from sandcastlegm.core.state import GameState, Scene
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry


def setup():
    rs = registry.create("sandcastle", rng=random.Random(7))
    state = GameState(ruleset_id="sandcastle")
    ctx = GMContext(ruleset=rs, state=state, log=EventLog())
    state.add_scene(Scene(title="場"))
    execute_tool(ctx, "create_map", {"name": "床", "width": 12, "height": 12, "cell_size_m": 2})
    return rs, state, ctx


def place(ctx, state, rs, name, x, y, is_pc):
    ch = rs.new_character(name, is_pc=is_pc)
    ch.is_pc = is_pc
    state.add_character(ch)
    execute_tool(ctx, "place_token", {"name": name, "x": x, "y": y,
                                      "kind": "pc" if is_pc else "enemy", "character_id": ch.id})
    return ch


def test_hits_only_inside_radius_and_spares_attacker():
    rs, state, ctx = setup()
    hero = place(ctx, state, rs, "アリア", 5, 5, is_pc=True)
    near = place(ctx, state, rs, "敵", 6, 5, is_pc=False)      # 1 cell = 2m away
    far = place(ctx, state, rs, "遠くの敵", 10, 5, is_pc=False)  # 5 cells = 10m away
    hp_near, hp_far, hp_hero = near.hp, far.hp, hero.hp

    out = execute_tool(ctx, "area_attack", {
        "attacker_id": hero.id, "name": "爆裂", "x": 5, "y": 5,
        "radius_m": 2, "damage": "1d1+3",  # deterministic 4 damage
    })
    assert "爆裂" in out
    assert near.hp == hp_near - 4
    assert far.hp == hp_far          # outside the radius
    assert hero.hp == hp_hero        # the attacker is never caught
    assert any(e.type == EventType.ROLL and "爆裂" in e.text for e in ctx.log.events)


def test_save_halves_or_negates():
    rs, state, ctx = setup()
    hero = place(ctx, state, rs, "アリア", 2, 2, is_pc=True)
    foe = place(ctx, state, rs, "敵", 3, 2, is_pc=False)
    hp0 = foe.hp

    # TN 3 cannot be missed on 3d6 with a non-negative ability → save succeeds, half of 4 = 2.
    execute_tool(ctx, "area_attack", {
        "attacker_id": hero.id, "x": 3, "y": 2, "radius_m": 2, "damage": "1d1+3",
        "save_ability": "DEX", "save_tn": 3,
    })
    assert foe.hp == hp0 - 2

    # on_save=none → a successful save negates entirely.
    hp1 = foe.hp
    execute_tool(ctx, "area_attack", {
        "attacker_id": hero.id, "x": 3, "y": 2, "radius_m": 2, "damage": "1d1+3",
        "save_ability": "DEX", "save_tn": 3, "on_save": "none",
    })
    assert foe.hp == hp1


def test_failed_save_takes_full_damage():
    rs, state, ctx = setup()
    hero = place(ctx, state, rs, "アリア", 2, 2, is_pc=True)
    foe = place(ctx, state, rs, "敵", 3, 2, is_pc=False)
    hp0 = foe.hp
    out = execute_tool(ctx, "area_attack", {
        "attacker_id": hero.id, "x": 3, "y": 2, "radius_m": 2, "damage": "1d1+3",
        "save_ability": "DEX", "save_tn": 99,  # unreachable → always fails
    })
    assert foe.hp == hp0 - 4
    assert "セーヴ失敗" in out


def test_friendly_fire_off_spares_own_side():
    rs, state, ctx = setup()
    hero = place(ctx, state, rs, "アリア", 5, 5, is_pc=True)
    ally = place(ctx, state, rs, "ボロミ", 5, 6, is_pc=True)
    foe = place(ctx, state, rs, "敵", 6, 5, is_pc=False)
    hp_ally, hp_foe = ally.hp, foe.hp

    execute_tool(ctx, "area_attack", {
        "attacker_id": hero.id, "x": 5, "y": 5, "radius_m": 4, "damage": "1d1+3",
        "friendly_fire": False,
    })
    assert ally.hp == hp_ally      # spared
    assert foe.hp == hp_foe - 4


def test_downed_and_empty_area():
    rs, state, ctx = setup()
    hero = place(ctx, state, rs, "アリア", 5, 5, is_pc=True)
    foe = place(ctx, state, rs, "敵", 6, 5, is_pc=False)
    foe.hp = 0
    out = execute_tool(ctx, "area_attack", {
        "attacker_id": hero.id, "x": 6, "y": 5, "radius_m": 2, "damage": "1d1+3",
    })
    assert "no targets" in out     # the downed foe is not re-rolled
    assert foe.hp == 0


def test_downing_marks_condition():
    rs, state, ctx = setup()
    hero = place(ctx, state, rs, "アリア", 5, 5, is_pc=True)
    foe = place(ctx, state, rs, "敵", 6, 5, is_pc=False)
    foe.hp = 3
    out = execute_tool(ctx, "area_attack", {
        "attacker_id": hero.id, "x": 6, "y": 5, "radius_m": 2, "damage": "1d1+3",
    })
    assert foe.hp == 0
    assert "戦闘不能" in foe.conditions
    assert "戦闘不能" in out
