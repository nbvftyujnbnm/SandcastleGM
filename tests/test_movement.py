import random

from sandcastlegm.core.events import EventLog
from sandcastlegm.core.state import GameState, Position, Scene, chebyshev, manhattan
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry


def test_distance_helpers():
    a, b = Position(1, 1), Position(4, 3)
    assert chebyshev(a, b) == 3      # max(3,2)
    assert manhattan(a, b) == 5      # 3 + 2 (diagonals cost double)


def setup_map():
    rs = registry.create("sandcastle", rng=random.Random(1))
    state = GameState(ruleset_id="sandcastle")
    ctx = GMContext(ruleset=rs, state=state, log=EventLog())
    state.add_scene(Scene(title="場"))
    execute_tool(ctx, "create_map", {"name": "床", "width": 12, "height": 12,
                                     "walls": [[5, 5]], "cell_size_m": 2})
    return rs, state, ctx


def test_move_within_allowance_and_over():
    rs, state, ctx = setup_map()
    hero = rs.new_character("アリア")  # move_m 10 -> 5 cells at 2m
    state.add_character(hero)
    execute_tool(ctx, "place_token", {"name": "アリア", "x": 0, "y": 0, "character_id": hero.id, "glyph": "@"})
    tok = next(iter(state.active_map.tokens.values()))

    ok = execute_tool(ctx, "move_token", {"token_id": tok.id, "x": 3, "y": 0})  # 6m
    assert "moved" in ok and tok.position.x == 3

    far = execute_tool(ctx, "move_token", {"token_id": tok.id, "x": 10, "y": 0})  # 14m > 10
    assert "移動力超過" in far and tok.position.x == 3  # not moved

    forced = execute_tool(ctx, "move_token", {"token_id": tok.id, "x": 10, "y": 0, "force": True})
    assert "moved" in forced and tok.position.x == 10


def test_move_blocked_by_wall_and_occupant():
    rs, state, ctx = setup_map()
    a = rs.new_character("A")
    b = rs.new_character("B")
    state.add_character(a)
    state.add_character(b)
    execute_tool(ctx, "place_token", {"name": "A", "x": 4, "y": 5, "character_id": a.id})
    execute_tool(ctx, "place_token", {"name": "B", "x": 6, "y": 5, "character_id": b.id})
    ta = state.active_map.token_for_character(a.id)

    assert "壁" in execute_tool(ctx, "move_token", {"token_id": ta.id, "x": 5, "y": 5})
    assert "占有" in execute_tool(ctx, "move_token", {"token_id": ta.id, "x": 6, "y": 5})
    assert "範囲外" in execute_tool(ctx, "move_token", {"token_id": ta.id, "x": 99, "y": 0})


def test_melee_requires_adjacency():
    rs, state, ctx = setup_map()
    a = rs.new_character("剣士", abilities={"STR": 2})
    foe = rs.create_monster("brown_bear")
    state.add_character(a)
    state.add_character(foe)
    execute_tool(ctx, "place_token", {"name": "剣士", "x": 1, "y": 1, "character_id": a.id})
    execute_tool(ctx, "place_token", {"name": "熊", "x": 6, "y": 1, "character_id": foe.id})

    out = execute_tool(ctx, "resolve_attack", {"attacker_id": a.id, "target_id": foe.id, "att": 5, "damage": "1d6", "reach": "近接"})
    assert "範囲外" in out and foe.hp == foe.max_hp  # too far, no damage

    # Move adjacent (diagonal ok for reach), then it connects.
    ta = state.active_map.token_for_character(a.id)
    execute_tool(ctx, "move_token", {"token_id": ta.id, "x": 5, "y": 1, "force": True})
    out2 = execute_tool(ctx, "resolve_attack", {"attacker_id": a.id, "target_id": foe.id, "att": 100, "damage": "1d6", "reach": "近接"})
    assert "範囲外" not in out2


def test_ranged_uses_range_m():
    rs, state, ctx = setup_map()
    archer = rs.new_character("射手", abilities={"PER": 2})
    foe = rs.create_monster("homunculus")
    state.add_character(archer)
    state.add_character(foe)
    execute_tool(ctx, "place_token", {"name": "射手", "x": 0, "y": 0, "character_id": archer.id})
    execute_tool(ctx, "place_token", {"name": "的", "x": 6, "y": 0, "character_id": foe.id})  # 12m

    near = execute_tool(ctx, "resolve_attack", {"attacker_id": archer.id, "target_id": foe.id,
                                                "att": 100, "damage": "1d6", "reach": "遠隔", "range_m": 20})
    assert "範囲外" not in near

    foe.hp = foe.max_hp
    far = execute_tool(ctx, "resolve_attack", {"attacker_id": archer.id, "target_id": foe.id,
                                               "att": 100, "damage": "1d6", "reach": "遠隔", "range_m": 8})
    assert "範囲外" in far and foe.hp == foe.max_hp


def test_range_skipped_when_not_on_map():
    rs = registry.create("sandcastle", rng=random.Random(1))
    state = GameState(ruleset_id="sandcastle")
    ctx = GMContext(ruleset=rs, state=state, log=EventLog())
    a = rs.new_character("A", abilities={"STR": 2})
    foe = rs.create_monster("homunculus")
    state.add_character(a)
    state.add_character(foe)
    # No map / no tokens -> range check skipped, attack resolves normally.
    out = execute_tool(ctx, "resolve_attack", {"attacker_id": a.id, "target_id": foe.id, "att": 100, "damage": "1d6"})
    assert "範囲外" not in out


def test_monster_move_parsed():
    rs = registry.create("sandcastle")
    assert rs.create_monster("brown_bear").sheet["move_m"] == 12
    assert rs.new_character("PC").sheet["move_m"] == 10
