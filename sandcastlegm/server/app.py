"""Multiplayer session server.

A thin real-time layer over the engine: each *room* owns one
:class:`~sandcastlegm.core.state.GameState`, its :class:`EventLog`, and an
:class:`~sandcastlegm.gm.engine.AIGameMaster`. Players connect over a WebSocket,
send actions, and receive every logged event live — so multiple players share
one AI-run table. The same room can also be exported to a virtual tabletop.

``SessionManager`` and ``Room`` have no web-framework dependency and are unit
testable on their own; :func:`create_app` builds the FastAPI app and imports
FastAPI lazily, so the rest of the package imports fine without the server extra.
"""

from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from typing import Any

from sandcastlegm.core.events import Event, EventLog
from sandcastlegm.core.state import GameState
from sandcastlegm.gm.engine import AIGameMaster
from sandcastlegm.rulesets import registry

# Imported at module scope so FastAPI can resolve the stringized ``WebSocket``
# annotation (this file uses ``from __future__ import annotations``) against the
# module globals. Guarded so the module still imports without the server extra.
try:
    from fastapi import WebSocket, WebSocketDisconnect
except ImportError:  # pragma: no cover - server extra not installed
    WebSocket = WebSocketDisconnect = None  # type: ignore[assignment,misc]


@dataclass
class Room:
    """One running game: state, log, GM, and connected player queues."""

    id: str
    gm: AIGameMaster
    # (queue, loop) per connected client. The loop is captured so we can wake a
    # waiting consumer from the worker thread that runs the (blocking) GM turn.
    subscribers: list[tuple[Any, Any]] = field(default_factory=list)

    @property
    def state(self) -> GameState:
        return self.gm.state

    @property
    def log(self) -> EventLog:
        return self.gm.log

    def subscribe(self, loop: Any) -> "asyncio.Queue[dict[str, Any]]":
        queue: "asyncio.Queue[dict[str, Any]]" = asyncio.Queue()
        self.subscribers.append((queue, loop))
        return queue

    def unsubscribe(self, queue: "asyncio.Queue[dict[str, Any]]") -> None:
        self.subscribers = [(q, lp) for (q, lp) in self.subscribers if q is not queue]

    def broadcast(self, event: Event) -> None:
        # Called from the event loop or from a GM worker thread; schedule the put
        # on each consumer's loop so it is thread-safe and wakes the consumer.
        payload = {"kind": "event", "event": event.to_dict()}
        for queue, loop in list(self.subscribers):
            loop.call_soon_threadsafe(queue.put_nowait, payload)


class SessionManager:
    """Owns all live rooms."""

    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}

    def create(self, ruleset_id: str, title: str = "Untitled Session") -> Room:
        ruleset = registry.create(ruleset_id, rng=random.Random())
        state = GameState(ruleset_id=ruleset_id, title=title)
        log = EventLog()
        gm = AIGameMaster(ruleset, state, log)
        room = Room(id=state.id, gm=gm)
        # Wire the log to the room's broadcaster so every event reaches players.
        log.subscribe(room.broadcast)
        self._rooms[room.id] = room
        return room

    def get(self, room_id: str) -> Room:
        if room_id not in self._rooms:
            raise KeyError(room_id)
        return self._rooms[room_id]

    def save(self, room_id: str, directory: str | None = None) -> str:
        from sandcastlegm.core.persistence import DEFAULT_DIR, save_session_to_dir

        room = self.get(room_id)
        return save_session_to_dir(room.state, room.log, directory or DEFAULT_DIR)

    def restore(self, path: str) -> Room:
        """Load a saved session into a new live room and register it."""
        from sandcastlegm.core.persistence import load_session

        state, log = load_session(path)
        ruleset = registry.create(state.ruleset_id, rng=random.Random())
        gm = AIGameMaster(ruleset, state, log)
        room = Room(id=state.id, gm=gm)
        log.subscribe(room.broadcast)
        self._rooms[room.id] = room
        return room

    def list(self) -> list[dict[str, Any]]:
        return [
            {"id": r.id, "title": r.state.title, "ruleset": r.state.ruleset_id,
             "players": len(r.state.player_characters())}
            for r in self._rooms.values()
        ]


def create_app(manager: SessionManager | None = None) -> Any:
    """Build the FastAPI app. Requires the ``server`` extra (fastapi, uvicorn)."""
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse, Response
    from starlette.concurrency import run_in_threadpool

    from sandcastlegm.server.spectator import index_page, watch_page
    from sandcastlegm.vtt import get_adapter

    mgr = manager or SessionManager()
    app = FastAPI(title="SandcastleGM", version="0.1.0")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return index_page()

    @app.get("/watch/{room_id}", response_class=HTMLResponse)
    def watch(room_id: str) -> str:
        return watch_page(room_id)

    @app.get("/sessions/{room_id}/board")
    def board(room_id: str) -> Any:
        try:
            room = mgr.get(room_id)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        grid = room.state.active_map
        if grid is None:
            return {"ascii": "", "grid": None}
        chars = room.state.characters
        tokens = []
        for t in grid.tokens.values():
            ch = chars.get(t.character_id) if t.character_id else None
            tokens.append({
                "id": t.id, "name": t.name, "x": t.position.x, "y": t.position.y,
                "glyph": t.glyph, "color": t.color, "kind": t.kind.value,
                "hidden": t.hidden,
                "hp": ch.hp if ch else None,
                "max_hp": ch.max_hp if ch else None,
                "downed": bool(ch and ch.hp <= 0),
            })
        return {
            "ascii": grid.render_ascii(reveal_hidden=True),
            "grid": {
                "name": grid.name, "width": grid.width, "height": grid.height,
                "cell_size_m": grid.cell_size_m,
                "terrain": dict(grid.terrain),
                "tokens": tokens,
            },
        }

    @app.get("/rulesets")
    def rulesets() -> dict[str, str]:
        return registry.available()

    @app.get("/sessions")
    def list_sessions() -> list[dict[str, Any]]:
        return mgr.list()

    @app.post("/sessions")
    def create_session(body: dict[str, Any]) -> dict[str, str]:
        room = mgr.create(body.get("ruleset_id", "sandcastle"), body.get("title", "Untitled Session"))
        return {"id": room.id, "ai_gm": "on" if room.gm.available else "referee-only"}

    @app.get("/sessions/{room_id}")
    def get_session(room_id: str) -> Any:
        try:
            return mgr.get(room_id).state.to_dict()
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)

    @app.get("/sessions/{room_id}/events")
    def get_events(room_id: str) -> Any:
        return mgr.get(room_id).log.to_list()

    @app.post("/sessions/{room_id}/characters")
    def add_character(room_id: str, body: dict[str, Any]) -> dict[str, str]:
        room = mgr.get(room_id)
        char = room.gm.ruleset.new_character(
            body["name"],
            controller=body.get("controller"),
            level=body.get("level", 1),
            subspecies=body.get("subspecies", "人間"),
            combat_style=body.get("combat_style", "ストライカー"),
            abilities=body.get("abilities", {}),
            skills=body.get("skills", []),
        )
        room.state.add_character(char)
        return {"id": char.id}

    @app.post("/sessions/{room_id}/save")
    def save_session_route(room_id: str) -> Any:
        try:
            path = mgr.save(room_id)
        except KeyError:
            return JSONResponse({"error": "not found"}, status_code=404)
        return {"saved": path}

    @app.post("/sessions/load")
    def load_session_route(body: dict[str, Any]) -> Any:
        path = body.get("path")
        if not path:
            return JSONResponse({"error": "path required"}, status_code=400)
        try:
            room = mgr.restore(path)
        except (FileNotFoundError, KeyError):
            return JSONResponse({"error": "save not found"}, status_code=404)
        return {"id": room.id, "ai_gm": "on" if room.gm.available else "referee-only"}

    @app.get("/sessions/{room_id}/export/{vtt}")
    def export_vtt(room_id: str, vtt: str) -> Any:
        room = mgr.get(room_id)
        adapter = get_adapter(vtt)
        payload = adapter.export_session(room.state)
        if isinstance(payload, bytes):
            return Response(
                content=payload,
                media_type="application/zip",
                headers={"Content-Disposition": f'attachment; filename="{room_id}.zip"'},
            )
        return JSONResponse(payload)

    @app.websocket("/sessions/{room_id}/ws")
    async def ws(websocket: WebSocket, room_id: str) -> None:
        await websocket.accept()
        try:
            room = mgr.get(room_id)
        except KeyError:
            await websocket.close(code=4004)
            return

        queue = room.subscribe(asyncio.get_running_loop())
        # Send the backlog so a late joiner sees the story so far.
        await websocket.send_json({"kind": "backlog", "events": room.log.to_list()})

        async def pump() -> None:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)

        pump_task = asyncio.create_task(pump())
        try:
            while True:
                msg = await websocket.receive_json()
                if msg.get("type") == "action":
                    # The GM call is synchronous (anthropic SDK); run off the loop.
                    await run_in_threadpool(
                        room.gm.turn, msg.get("text", ""), msg.get("actor_id")
                    )
        except WebSocketDisconnect:
            pass
        finally:
            pump_task.cancel()
            room.unsubscribe(queue)

    return app
