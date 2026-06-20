import random

from sandcastlegm.core.events import EventLog
from sandcastlegm.core.state import GameState
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry


def setup():
    rs = registry.create("sandcastle", rng=random.Random(8))
    state = GameState(ruleset_id="sandcastle")
    ctx = GMContext(ruleset=rs, state=state, log=EventLog())
    return rs, state, ctx


def test_pc_has_pp_max_pp():
    rs, *_ = setup()
    pc = rs.new_character("アリア", level=3)
    assert pc.sheet["max_pp"] == 4 and pc.sheet["pp"] == 4  # 1 + level


def test_rest_restores_hp_pp_and_clears_effects():
    rs, state, ctx = setup()
    pc = rs.new_character("アリア", level=2)
    state.add_character(pc)
    pc.hp = 1
    pc.sheet["pp"] = 0
    execute_tool(ctx, "apply_effect", {"character_id": pc.id, "hex": "攻撃弱体ヘックス"})
    assert pc.conditions and pc.sheet["effects"]

    out = execute_tool(ctx, "rest", {})
    assert "アリア" in out
    assert pc.hp == pc.max_hp
    assert pc.sheet["pp"] == pc.sheet["max_pp"]
    assert pc.conditions == [] and pc.sheet["effects"] == []


def test_rest_defaults_to_pcs_only():
    rs, state, ctx = setup()
    pc = rs.new_character("アリア")
    foe = rs.create_monster("brown_bear")
    state.add_character(pc)
    state.add_character(foe)
    pc.hp = 1
    foe.hp = 1
    execute_tool(ctx, "rest", {})
    assert pc.hp == pc.max_hp
    assert foe.hp == 1  # enemy not rested by default


def test_rest_all_includes_enemies():
    rs, state, ctx = setup()
    foe = rs.create_monster("brown_bear")
    state.add_character(foe)
    foe.hp = 1
    execute_tool(ctx, "rest", {"all": True})
    assert foe.hp == foe.max_hp
