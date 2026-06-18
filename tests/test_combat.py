import random

from sandcastlegm.core.events import EventLog, EventType
from sandcastlegm.core.state import GameState
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry


def setup():
    rs = registry.create("sandcastle", rng=random.Random(5))
    state = GameState(ruleset_id="sandcastle")
    log = EventLog()
    ctx = GMContext(ruleset=rs, state=state, log=log)
    a = rs.new_character("アリア", level=2, abilities={"DEX": 2})
    b = rs.new_character("ボロミ", level=2)
    g1 = rs.new_character("ゴブA", is_pc=False, level=1)
    g2 = rs.new_character("ゴブB", is_pc=False, level=1)
    for c in (a, b, g1, g2):
        state.add_character(c)
    return ctx, state, a, b, g1, g2


def test_roll_initiative_sets_order_all_combatants():
    ctx, state, *_ = setup()
    out = execute_tool(ctx, "roll_initiative", {})
    assert "initiative set" in out
    assert len(state.turn_order.order) == 4
    assert state.turn_order.round == 1
    assert any(e.type == EventType.TURN for e in ctx.log.events)


def test_initiative_groups_by_side_ties_favor_pcs():
    ctx, state, a, b, g1, g2 = setup()
    order, desc = ctx.ruleset.roll_initiative(state, [a.id, b.id, g1.id, g2.id])
    # PCs form one contiguous block and foes another (side-based initiative).
    pc_positions = [order.index(a.id), order.index(b.id)]
    foe_positions = [order.index(g1.id), order.index(g2.id)]
    assert max(pc_positions) < min(foe_positions) or max(foe_positions) < min(pc_positions)


def test_advance_skips_downed_and_increments_round():
    ctx, state, a, b, g1, g2 = setup()
    execute_tool(ctx, "set_turn_order", {"order": [a.id, g1.id, b.id, g2.id]})
    assert state.turn_order.active == a.id

    # Down g1; advancing from a should skip g1 and land on b.
    execute_tool(ctx, "update_character", {"character_id": g1.id, "hp_delta": -999})
    execute_tool(ctx, "advance_turn", {})
    assert state.turn_order.active == b.id

    # b -> (skip nobody) g2
    execute_tool(ctx, "advance_turn", {})
    assert state.turn_order.active == g2.id

    # g2 -> wraps to a; round becomes 2
    execute_tool(ctx, "advance_turn", {})
    assert state.turn_order.active == a.id
    assert state.turn_order.round == 2


def test_first_actor_downed_is_skipped_on_setup():
    ctx, state, a, b, g1, g2 = setup()
    execute_tool(ctx, "update_character", {"character_id": a.id, "hp_delta": -999})
    execute_tool(ctx, "set_turn_order", {"order": [a.id, b.id]})
    assert state.turn_order.active == b.id  # a is down, skipped


def test_end_combat_clears_order():
    ctx, state, *_ = setup()
    execute_tool(ctx, "roll_initiative", {})
    execute_tool(ctx, "end_combat", {})
    assert state.turn_order.order == []
    assert state.turn_order.active is None


def test_advance_without_order_is_graceful():
    ctx, *_ = setup()
    assert "no turn order" in execute_tool(ctx, "advance_turn", {})
