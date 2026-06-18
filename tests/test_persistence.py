import random

from sandcastlegm.core.events import Event, EventLog, EventType
from sandcastlegm.core.persistence import (
    from_payload,
    load_session,
    save_session,
    to_payload,
)
from sandcastlegm.core.state import GameState
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry


def build_session():
    rs = registry.create("sandcastle", rng=random.Random(9))
    state = GameState(ruleset_id="sandcastle", title="保存テスト")
    log = EventLog()
    ctx = GMContext(ruleset=rs, state=state, log=log)
    hero = rs.new_character("アリア", abilities={"DEX": 2}, skills=["体術"])
    state.add_character(hero)
    execute_tool(ctx, "set_scene", {"title": "洞窟", "exits": ["北"]})
    execute_tool(ctx, "create_map", {"name": "洞窟", "width": 6, "height": 5, "walls": [[0, 0]]})
    execute_tool(ctx, "place_token", {"name": "アリア", "x": 1, "y": 1, "kind": "pc", "character_id": hero.id})
    goblin = rs.new_character("ゴブ", is_pc=False, level=1)
    state.add_character(goblin)
    execute_tool(ctx, "roll_initiative", {})
    execute_tool(ctx, "update_character", {"character_id": goblin.id, "hp_delta": -3, "add_conditions": ["出血"]})
    log.append(Event(type=EventType.NARRATION, text="洞窟に踏み込んだ。"))
    return state, log, hero, goblin


def test_round_trip_preserves_everything():
    state, log, hero, goblin = build_session()
    state2, log2 = from_payload(to_payload(state, log))

    assert state2.to_dict() == state.to_dict()
    assert log2.to_list() == log.to_list()
    # Spot-check reconstructed objects, not just dict equality.
    assert state2.title == "保存テスト"
    assert state2.characters[hero.id].sheet["abilities"]["DEX"] == 2
    assert state2.characters[goblin.id].conditions == ["出血"]
    assert state2.current_scene.title == "洞窟"
    grid = state2.active_map
    assert grid is not None and grid.terrain["0,0"] == "wall"
    assert any(t.character_id == hero.id for t in grid.tokens.values())
    assert state2.turn_order.order == state.turn_order.order


def test_save_and_load_file(tmp_path):
    state, log, *_ = build_session()
    path = save_session(state, log, tmp_path / "s.json")
    state2, log2 = load_session(path)
    assert state2.id == state.id
    assert len(log2.events) == len(log.events)


def test_reconstructed_state_is_playable(tmp_path):
    """After loading, the ruleset can still resolve checks against the sheet."""
    from sandcastlegm.rulesets.base import CheckRequest

    state, log, hero, _ = build_session()
    state2, _ = load_session(save_session(state, log, tmp_path / "s.json"))
    rs = registry.create("sandcastle", rng=random.Random(1))
    result = rs.resolve_check(state2, CheckRequest(actor_id=hero.id, ability="DEX", target_number=3))
    assert result.total == result.roll.total + 2  # DEX +2 from the restored sheet
