import io
import json
import xml.etree.ElementTree as ET
import zipfile

from sandcastlegm.core.state import GameState, MapGrid, Position, Token, TokenKind
from sandcastlegm.rulesets import registry
from sandcastlegm.vtt import get_adapter


def build_state():
    rs = registry.create("sandcastle")
    state = GameState(ruleset_id="sandcastle", title="Demo")
    hero = rs.new_character("Hero", abilities={"STR": 1}, skills=["体術"])
    state.add_character(hero)
    grid = MapGrid(name="Cave", width=8, height=8)
    grid.add_token(Token(name="Hero", position=Position(1, 1), kind=TokenKind.PC,
                         character_id=hero.id, glyph="@"))
    state.add_map(grid)
    from sandcastlegm.core.state import Scene
    scene = state.add_scene(Scene(title="Cave mouth"))
    scene.map_id = grid.id
    return state, hero


def test_cocofolia_character_clipboard_is_valid_json():
    state, hero = build_state()
    adapter = get_adapter("cocofolia")
    clip = adapter.export_character_clipboard(hero)
    data = json.loads(clip)
    assert data["kind"] == "character"
    assert data["data"]["name"] == "Hero"
    assert data["data"]["status"][0]["label"] == "HP"
    # Abilities exported as params.
    labels = {p["label"] for p in data["data"]["params"]}
    assert "STR" in labels


def test_udonarium_character_is_wellformed_xml():
    state, hero = build_state()
    adapter = get_adapter("udonarium")
    xml = adapter.export_character(hero, x=1, y=1)
    root = ET.fromstring(xml)
    assert root.tag == "character"
    assert root.attrib["location.x"] == "50"  # 1 cell * grid size 50


def test_udonarium_session_zip_contains_objects():
    state, hero = build_state()
    adapter = get_adapter("udonarium")
    blob = adapter.export_session(state)
    assert isinstance(blob, bytes)
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = zf.namelist()
    assert any(n.startswith("character_") for n in names)
    assert any(n.startswith("map_") for n in names)


def test_unknown_adapter_raises():
    import pytest
    with pytest.raises(KeyError):
        get_adapter("roll20")
