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

    sid = client.post("/sessions", json={"ruleset_id": "sandcastle"}).json()["id"]

    # Watch page embeds the room id and the live-update wiring.
    watch = client.get(f"/watch/{sid}")
    assert watch.status_code == 200
    assert sid in watch.text
    assert "/ws" in watch.text and "refreshState" in watch.text

    # Board is empty until a map exists, then renders it.
    assert client.get(f"/sessions/{sid}/board").json() == {"ascii": ""}
    room = mgr.get(sid)
    ctx = GMContext(ruleset=room.gm.ruleset, state=room.state, log=room.log)
    execute_tool(ctx, "set_scene", {"title": "Hall"})
    execute_tool(ctx, "create_map", {"name": "Hall", "width": 4, "height": 3})
    ascii_board = client.get(f"/sessions/{sid}/board").json()["ascii"]
    assert ascii_board and "\n" in ascii_board


def test_vtt_export_endpoints():
    client = make_client()
    sid = client.post("/sessions", json={"ruleset_id": "sandcastle"}).json()["id"]
    client.post(f"/sessions/{sid}/characters", json={"name": "Aria"})

    cof = client.get(f"/sessions/{sid}/export/cocofolia").json()
    assert len(cof["characters"]) == 1

    udon = client.get(f"/sessions/{sid}/export/udonarium")
    assert udon.headers["content-type"] == "application/zip"
    assert len(udon.content) > 0
