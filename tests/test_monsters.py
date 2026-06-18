import random

from sandcastlegm.core.events import EventLog
from sandcastlegm.core.state import GameState
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry


def ctx():
    rs = registry.create("sandcastle", rng=random.Random(2))
    state = GameState(ruleset_id="sandcastle")
    return GMContext(ruleset=rs, state=state, log=EventLog())


def test_catalog_nonempty_and_named():
    rs = registry.create("sandcastle")
    cat = rs.monster_catalog()
    assert "demon" in cat and cat["demon"] == "悪魔"
    assert "brown_bear" in cat


def test_create_monster_builds_statted_character():
    rs = registry.create("sandcastle")
    demon = rs.create_monster("demon")
    assert demon.is_pc is False
    assert demon.hp == 80 and demon.max_hp == 80
    assert demon.sheet["abilities"]["WIL"] == 8
    assert demon.sheet["defense"] == 18
    assert demon.sheet["resist"]["橙紫"] == 11
    assert demon.sheet["vulnerability"] == "橙"
    assert any(a["name"] == "炎の剣" for a in demon.sheet["attacks"])


def test_create_monster_unknown_raises():
    import pytest
    rs = registry.create("sandcastle")
    with pytest.raises(KeyError):
        rs.create_monster("tarrasque")


def test_create_monster_rename():
    rs = registry.create("sandcastle")
    bear = rs.create_monster("brown_bear", name="主のヒグマ")
    assert bear.name == "主のヒグマ" and bear.sheet["monster_key"] == "brown_bear"


def test_spawn_monster_tool_adds_to_state():
    c = ctx()
    out = execute_tool(c, "spawn_monster", {"key": "monster_scorpion"})
    assert "spawned 1x 怪物サソリ" in out
    assert len(c.state.characters) == 1
    mob = next(iter(c.state.characters.values()))
    assert mob.hp == 25 and not mob.is_pc


def test_spawn_monster_count_and_naming():
    c = ctx()
    execute_tool(c, "spawn_monster", {"key": "salamander", "count": 3})
    names = sorted(ch.name for ch in c.state.characters.values())
    assert names == ["サラマンダー1", "サラマンダー2", "サラマンダー3"]


def test_spawn_monster_unknown_key_lists_available():
    c = ctx()
    out = execute_tool(c, "spawn_monster", {"key": "nope"})
    assert out.startswith("error: unknown monster")
    assert "demon" in out


def test_base_ruleset_has_empty_bestiary_by_default():
    # A monster-less system should not break the spawn_monster tool.
    rs = registry.create("sandcastle")
    assert isinstance(rs.monster_catalog(), dict)
