import random

from sandcastlegm.core.events import EventLog, EventType
from sandcastlegm.core.state import GameState, Scene
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry


def setup():
    rs = registry.create("sandcastle", rng=random.Random(1))
    state = GameState(ruleset_id="sandcastle")
    ctx = GMContext(ruleset=rs, state=state, log=EventLog())
    state.add_scene(Scene(title="場"))
    execute_tool(ctx, "create_map", {"name": "床", "width": 12, "height": 12, "cell_size_m": 2})
    return rs, state, ctx


def place(ctx, state, rs, name, x, y, is_pc, monster=None):
    if monster:
        ch = rs.create_monster(monster, name=name)
    else:
        ch = rs.new_character(name, is_pc=is_pc)
    ch.is_pc = is_pc
    state.add_character(ch)
    execute_tool(ctx, "place_token", {"name": name, "x": x, "y": y,
                                      "kind": "pc" if is_pc else "enemy", "character_id": ch.id})
    return ch, state.active_map.token_for_character(ch.id)


def test_leaving_reach_provokes():
    rs, state, ctx = setup()
    hero, htok = place(ctx, state, rs, "アリア", 5, 5, is_pc=True)
    foe, _ = place(ctx, state, rs, "敵", 6, 5, is_pc=False)  # adjacent

    out = execute_tool(ctx, "move_token", {"token_id": htok.id, "x": 5, "y": 8, "force": True})
    assert "opportunity attack from" in out and "敵" in out
    assert any(e.type == EventType.TURN and "機会攻撃" in e.text for e in ctx.log.events)


def test_staying_adjacent_does_not_provoke():
    rs, state, ctx = setup()
    hero, htok = place(ctx, state, rs, "アリア", 5, 5, is_pc=True)
    place(ctx, state, rs, "敵", 6, 5, is_pc=False)
    # Move to a cell still adjacent to the foe (diagonal neighbour).
    out = execute_tool(ctx, "move_token", {"token_id": htok.id, "x": 6, "y": 6, "force": True})
    assert "opportunity attack" not in out


def test_allies_do_not_provoke():
    rs, state, ctx = setup()
    hero, htok = place(ctx, state, rs, "アリア", 5, 5, is_pc=True)
    place(ctx, state, rs, "ボロミ", 6, 5, is_pc=True)  # ally adjacent
    out = execute_tool(ctx, "move_token", {"token_id": htok.id, "x": 5, "y": 9, "force": True})
    assert "opportunity attack" not in out


def test_downed_foe_does_not_provoke():
    rs, state, ctx = setup()
    hero, htok = place(ctx, state, rs, "アリア", 5, 5, is_pc=True)
    foe, _ = place(ctx, state, rs, "敵", 6, 5, is_pc=False)
    foe.hp = 0
    out = execute_tool(ctx, "move_token", {"token_id": htok.id, "x": 5, "y": 9, "force": True})
    assert "opportunity attack" not in out
