"""Multiplayer server tests. Skipped unless the `server` extra is installed."""

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

from sandcastlegm.server.app import SessionManager, create_app  # noqa: E402


def make_client():
    return TestClient(create_app(SessionManager()))


def test_session_lifecycle_and_characters():
    client = make_client()
    assert "sandcastle" in client.get("/rulesets").json()

    info = client.post("/sessions", json={"ruleset_id": "sandcastle", "title": "T"}).json()
    sid = info["id"]
    assert info["ai_gm"] == "referee-only"  # no API key in test env

    cid = client.post(f"/sessions/{sid}/characters", json={"name": "Aria"}).json()["id"]
    state = client.get(f"/sessions/{sid}").json()
    assert cid in state["characters"]
    assert client.get("/sessions/unknown").status_code == 404


def test_two_players_share_broadcasts():
    client = make_client()
    sid = client.post("/sessions", json={"ruleset_id": "sandcastle"}).json()["id"]
    a = client.post(f"/sessions/{sid}/characters", json={"name": "Aria"}).json()["id"]
    b = client.post(f"/sessions/{sid}/characters", json={"name": "Boromi"}).json()["id"]

    with client.websocket_connect(f"/sessions/{sid}/ws") as ws_a, \
         client.websocket_connect(f"/sessions/{sid}/ws") as ws_b:
        assert ws_a.receive_json()["kind"] == "backlog"
        assert ws_b.receive_json()["kind"] == "backlog"

        # An action by A reaches both A and B as the same event.
        ws_a.send_json({"type": "action", "text": "Aria listens at the door", "actor_id": a})
        ev_a = ws_a.receive_json()["event"]
        ev_b = ws_b.receive_json()["event"]
        assert ev_a["type"] == "player_action"
        assert ev_a["id"] == ev_b["id"]
        assert ev_a["text"] == "Aria listens at the door"

        # And an action by B reaches both.
        ws_b.send_json({"type": "action", "text": "Boromi draws his blade", "actor_id": b})
        assert ws_a.receive_json()["event"]["id"] == ws_b.receive_json()["event"]["id"]

    assert len(client.get(f"/sessions/{sid}/events").json()) == 2


def test_spectator_pages_and_board():
    from sandcastlegm.gm.tools import GMContext, execute_tool

    mgr = SessionManager()
    client = TestClient(create_app(mgr))

    idx = client.get("/")
    assert idx.status_code == 200
    assert "SandcastleGM" in idx.text
    assert "text/html" in idx.headers["content-type"]
    assert "loadRooms" in idx.text  # lobby room list

    # The /sessions list (consumed by the lobby) reflects created rooms.
    before = len(client.get("/sessions").json())

    sid = client.post("/sessions", json={"ruleset_id": "sandcastle"}).json()["id"]
    rooms = client.get("/sessions").json()
    assert len(rooms) == before + 1
    assert any(r["id"] == sid and "players" in r for r in rooms)

    # Watch page embeds the room id and the live-update wiring.
    watch = client.get(f"/watch/{sid}")
    assert watch.status_code == 200
    assert sid in watch.text
    assert "/ws" in watch.text and "refreshState" in watch.text

    # Watch page includes the graphical grid renderer.
    assert "renderBoard" in watch.text and 'class="board"' in watch.text

    # Board is empty until a map exists, then returns ascii + structured grid.
    empty = client.get(f"/sessions/{sid}/board").json()
    assert empty["ascii"] == "" and empty["grid"] is None

    room = mgr.get(sid)
    ctx = GMContext(ruleset=room.gm.ruleset, state=room.state, log=room.log)
    hero = room.gm.ruleset.new_character("Aria")
    room.state.add_character(hero)
    execute_tool(ctx, "set_scene", {"title": "Hall"})
    execute_tool(ctx, "create_map", {"name": "Hall", "width": 4, "height": 3, "walls": [[0, 0]]})
    execute_tool(ctx, "place_token", {"name": "Aria", "x": 2, "y": 1, "kind": "pc",
                                      "character_id": hero.id, "glyph": "@"})

    board = client.get(f"/sessions/{sid}/board").json()
    assert board["ascii"] and "\n" in board["ascii"]
    grid = board["grid"]
    assert grid["width"] == 4 and grid["height"] == 3
    assert grid["terrain"]["0,0"] == "wall"
    tok = next(t for t in grid["tokens"] if t["name"] == "Aria")
    assert (tok["x"], tok["y"]) == (2, 1)
    assert tok["hp"] == hero.hp and tok["max_hp"] == hero.max_hp and tok["downed"] is False


def test_save_and_load_session(tmp_path, monkeypatch):
    monkeypatch.setenv("SANDCASTLEGM_SAVE_DIR", str(tmp_path))
    mgr = SessionManager()
    client = TestClient(create_app(mgr))

    sid = client.post("/sessions", json={"ruleset_id": "sandcastle", "title": "保存"}).json()["id"]
    client.post(f"/sessions/{sid}/characters", json={"name": "Aria"})

    saved = client.post(f"/sessions/{sid}/save").json()
    assert "saved" in saved and saved["saved"].endswith(".json")

    # Load it back into a (fresh) manager-backed app.
    loaded = client.post("/sessions/load", json={"path": saved["saved"]}).json()
    assert loaded["id"] == sid  # same game id preserved
    state = client.get(f"/sessions/{loaded['id']}").json()
    assert state["title"] == "保存"
    assert len(state["characters"]) == 1

    assert client.post("/sessions/load", json={"path": str(tmp_path / "nope.json")}).status_code == 404
    assert client.post("/sessions/load", json={}).status_code == 400


def test_websocket_tool_move_token():
    from sandcastlegm.gm.tools import GMContext, execute_tool

    mgr = SessionManager()
    client = TestClient(create_app(mgr))
    sid = client.post("/sessions", json={"ruleset_id": "sandcastle"}).json()["id"]
    room = mgr.get(sid)
    ctx = GMContext(ruleset=room.gm.ruleset, state=room.state, log=room.log)
    execute_tool(ctx, "set_scene", {"title": "床"})
    execute_tool(ctx, "create_map", {"name": "床", "width": 8, "height": 8, "cell_size_m": 2})
    execute_tool(ctx, "place_token", {"name": "駒", "x": 0, "y": 0, "glyph": "@"})
    tok_id = next(iter(room.state.active_map.tokens))

    with client.websocket_connect(f"/sessions/{sid}/ws") as ws:
        ws.receive_json()  # backlog
        ws.send_json({"type": "tool", "name": "move_token", "input": {"token_id": tok_id, "x": 2, "y": 1, "force": True}})
        ev = ws.receive_json()["event"]
        assert ev["type"] == "map"
    assert room.state.active_map.tokens[tok_id].position.x == 2

    # A non-whitelisted tool over the WS is ignored (no spawn).
    before = len(room.state.characters)
    with client.websocket_connect(f"/sessions/{sid}/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "tool", "name": "spawn_monster", "input": {"key": "demon"}})
        # nothing should be broadcast for the ignored tool; send a valid move to get an event
        ws.send_json({"type": "tool", "name": "move_token", "input": {"token_id": tok_id, "x": 3, "y": 1, "force": True}})
        assert ws.receive_json()["event"]["type"] == "map"
    assert len(room.state.characters) == before  # demon was not spawned


def test_watch_page_has_click_move():
    client = make_client()
    sid = client.post("/sessions", json={"ruleset_id": "sandcastle"}).json()["id"]
    page = client.get(f"/watch/{sid}").text
    assert "sendTool" in page and "selectedToken" in page


def test_watch_page_has_pc_creation():
    client = make_client()
    sid = client.post("/sessions", json={"ruleset_id": "sandcastle"}).json()["id"]
    page = client.get(f"/watch/{sid}").text
    # The panel offers in-browser PC creation wired to the characters endpoint.
    assert "createPc" in page and 'id="pcname"' in page
    assert "ストライカー" in page and "ハリアー" in page

    # The endpoint it posts to honours the form's fields.
    body = {"name": "リオ", "subspecies": "エルフ", "combat_style": "ヘクサー", "level": 3}
    cid = client.post(f"/sessions/{sid}/characters", json=body).json()["id"]
    state = client.get(f"/sessions/{sid}").json()
    sheet = state["characters"][cid]["sheet"]
    assert sheet["subspecies"] == "エルフ"
    assert sheet["combat_style"] == "ヘクサー"
    assert sheet["level"] == 3


def test_vtt_export_endpoints():
    client = make_client()
    sid = client.post("/sessions", json={"ruleset_id": "sandcastle"}).json()["id"]
    client.post(f"/sessions/{sid}/characters", json={"name": "Aria"})

    cof = client.get(f"/sessions/{sid}/export/cocofolia").json()
    assert len(cof["characters"]) == 1

    udon = client.get(f"/sessions/{sid}/export/udonarium")
    assert udon.headers["content-type"] == "application/zip"
    assert len(udon.content) > 0
