import random
import json

from sandcastlegm.core.events import EventLog, EventType
from sandcastlegm.core.state import GameState
from sandcastlegm.gm.engine import AIGameMaster
from sandcastlegm.gm.providers import LLMProvider, LLMResponse, LLMToolCall
from sandcastlegm.gm.tools import GMContext, TOOL_SPECS, execute_tool, tool_names
from sandcastlegm.rulesets import registry


def make_ctx():
    rs = registry.create("sandcastle", rng=random.Random(3))
    state = GameState(ruleset_id="sandcastle")
    log = EventLog()
    return GMContext(ruleset=rs, state=state, log=log)


def test_tool_specs_have_unique_names_and_schemas():
    names = [s["name"] for s in TOOL_SPECS]
    assert len(names) == len(set(names))
    assert tool_names() == set(names)
    for spec in TOOL_SPECS:
        assert "input_schema" in spec and spec["input_schema"]["type"] == "object"


def test_set_scene_and_create_map_flow():
    ctx = make_ctx()
    execute_tool(ctx, "set_scene", {"title": "The Crumbling Bridge", "location": "ravine"})
    assert ctx.state.current_scene.title == "The Crumbling Bridge"

    out = execute_tool(ctx, "create_map", {"name": "Bridge", "width": 10, "height": 6,
                                           "walls": [[0, 0], [1, 0]]})
    assert "map created" in out
    grid = ctx.state.active_map
    assert grid is not None and grid.terrain["0,0"] == "wall"

    execute_tool(ctx, "place_token", {"name": "Hero", "x": 2, "y": 3, "kind": "pc", "glyph": "@"})
    assert len(grid.tokens) == 1


def test_roll_check_logs_and_returns_json():
    ctx = make_ctx()
    actor = ctx.ruleset.new_character("Hero", abilities={"STR": 2})
    ctx.state.add_character(actor)
    out = execute_tool(ctx, "roll_check", {"actor_id": actor.id, "ability": "STR",
                                           "target_number": 3, "description": "force the door"})
    data = json.loads(out)
    assert data["success"] is True
    assert any(e.type == EventType.ROLL for e in ctx.log.events)


def test_update_character_clamps_hp():
    ctx = make_ctx()
    npc = ctx.ruleset.new_character("Goblin", is_pc=False, level=1)
    ctx.state.add_character(npc)
    execute_tool(ctx, "update_character", {"character_id": npc.id, "hp_delta": -9999})
    assert npc.hp == 0
    execute_tool(ctx, "update_character", {"character_id": npc.id, "hp_delta": 9999})
    assert npc.hp == npc.max_hp


def test_turn_order_advances():
    ctx = make_ctx()
    a = ctx.ruleset.new_character("A")
    b = ctx.ruleset.new_character("B")
    ctx.state.add_character(a)
    ctx.state.add_character(b)
    execute_tool(ctx, "set_turn_order", {"order": [a.id, b.id]})
    assert ctx.state.turn_order.active == a.id
    execute_tool(ctx, "advance_turn", {})
    assert ctx.state.turn_order.active == b.id
    execute_tool(ctx, "advance_turn", {})
    assert ctx.state.turn_order.active == a.id and ctx.state.turn_order.round == 2


def test_unknown_tool_is_handled():
    ctx = make_ctx()
    assert execute_tool(ctx, "nope", {}).startswith("error")


def test_engine_degraded_mode_without_provider():
    rs = registry.create("sandcastle", rng=random.Random(1))
    state = GameState(ruleset_id="sandcastle")
    gm = AIGameMaster(rs, state, provider=None)  # explicit None -> referee mode
    assert gm.available is False
    turn = gm.turn("I look around.")
    assert turn.degraded
    assert any(e.type == EventType.PLAYER_ACTION for e in turn.events)


def test_engine_drives_a_mock_provider():
    """A fake provider exercises the full vendor-neutral tool-use loop offline."""
    rs = registry.create("sandcastle", rng=random.Random(1))
    state = GameState(ruleset_id="sandcastle")
    gm = AIGameMaster(rs, state, provider=_MockProvider())
    assert gm.available is True
    turn = gm.turn("I kick the door.")
    assert "The door bursts open" in turn.narration
    assert state.current_scene is not None  # the mock called set_scene
    assert any(e.type == EventType.SCENE for e in gm.log.events)


class _MockProvider(LLMProvider):
    """Minimal provider: first turn calls a tool, second narrates."""

    name = "mock"

    def __init__(self):
        self._calls = 0
        self.history = []

    @property
    def available(self) -> bool:
        return True

    def add_user(self, text: str) -> None:
        self.history.append(("user", text))

    def add_tool_results(self, results) -> None:
        self.history.append(("tool", results))

    def generate(self, system: str, tools_spec) -> LLMResponse:
        self._calls += 1
        if self._calls == 1:
            return LLMResponse(
                text="",
                tool_calls=[
                    LLMToolCall(id="t1", name="set_scene",
                                args={"title": "Doorway", "narrative": "A heavy door."})
                ],
            )
        return LLMResponse(text="The door bursts open.", tool_calls=[])
