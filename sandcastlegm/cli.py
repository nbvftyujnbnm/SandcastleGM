"""Command-line entry point: play a local session, list systems, or serve.

    sandcastlegm rulesets                 # list installed rulesets
    sandcastlegm play [--ruleset ID]      # play a local session in the terminal
    sandcastlegm serve [--host H --port P]# run the multiplayer server

The ``play`` loop works with or without an API key. With one, the AI GM
narrates; without, it runs as a referee and you drive the dice yourself with the
slash commands below.
"""

from __future__ import annotations

import argparse
import random
import sys

from sandcastlegm.core.events import EventLog, EventType
from sandcastlegm.core.state import GameState
from sandcastlegm.gm.engine import AIGameMaster
from sandcastlegm.gm.tools import GMContext, execute_tool
from sandcastlegm.rulesets import registry
from sandcastlegm.rulesets.base import CheckRequest

HELP = """\
Commands:
  <text>                 speak / act — sent to the AI GM
  /check ABILITY [TN] [SKILL]   roll an ability check for your character
  /roll EXPR             roll dice, e.g. /roll 2d6+1
  /sheet                 show your character sheet
  /state                 show the current scene, characters, and map
  /export VTT PATH       export the session (VTT = cocofolia | udonarium)
  /help                  show this help
  /quit                  leave
"""


def _print_event(event) -> None:
    tag = {
        EventType.NARRATION: "GM",
        EventType.DIALOGUE: "GM",
        EventType.ROLL: "🎲",
        EventType.SCENE: "🎬",
        EventType.MAP: "🗺",
        EventType.TURN: "⚔",
        EventType.SYSTEM: "·",
        EventType.PLAYER_ACTION: ">",
    }.get(event.type, "·")
    if event.type == EventType.PLAYER_ACTION:
        return  # already echoed by the player typing it
    print(f"  {tag} {event.text}")


def cmd_rulesets(_: argparse.Namespace) -> int:
    print("Installed rulesets:")
    for rid, name in registry.available().items():
        print(f"  {rid:<14} {name}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("The server requires extras: pip install 'sandcastlegm[server]'", file=sys.stderr)
        return 1
    from sandcastlegm.server.app import create_app

    uvicorn.run(create_app(), host=args.host, port=args.port)
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    if args.ruleset not in registry.available():
        print(f"Unknown ruleset {args.ruleset!r}. Try: {', '.join(registry.available())}")
        return 1

    ruleset = registry.create(args.ruleset, rng=random.Random())
    state = GameState(ruleset_id=args.ruleset, title=args.title)
    log = EventLog()
    log.subscribe(_print_event)
    gm = AIGameMaster(ruleset, state, log)

    # Quick character creation.
    name = input("Your character's name [Hero]: ").strip() or "Hero"
    pc = ruleset.new_character(name, controller="local")
    state.add_character(pc)

    print()
    print(f"=== {state.title} — {ruleset.name} ===")
    print(f"AI GM: {'on' if gm.available else 'OFF (referee mode — set ANTHROPIC_API_KEY for narration)'}")
    print(HELP)
    if gm.available:
        gm.turn("(The players are ready. Open the adventure with an evocative first scene.)")

    ctx = GMContext(ruleset=ruleset, state=state, log=log)
    while True:
        try:
            line = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ("/quit", "/exit"):
            break
        if line == "/help":
            print(HELP)
        elif line == "/sheet":
            _show_sheet(pc)
        elif line == "/state":
            from sandcastlegm.gm.prompts import render_state_snapshot
            print(render_state_snapshot(state))
        elif line.startswith("/roll"):
            expr = line[len("/roll"):].strip() or "3d6"
            # roll_dice logs the result, which the event subscriber prints.
            execute_tool(ctx, "roll_dice", {"expression": expr})
        elif line.startswith("/check"):
            _do_check(ruleset, state, ctx, pc, line)
        elif line.startswith("/export"):
            _do_export(state, line)
        else:
            turn = gm.turn(line, actor_id=pc.id)
            if turn.degraded:
                print("  " + turn.narration)

    print("Session ended.")
    return 0


def _show_sheet(pc) -> None:
    s = pc.sheet
    print(f"  {pc.name} — {s.get('subspecies', '')} {s.get('combat_style', '')} L{s.get('level', '?')}")
    print(f"  HP {pc.hp}/{pc.max_hp}  bab {s.get('bab', 0)}")
    print("  Abilities: " + "  ".join(f"{k}{v:+d}" for k, v in s.get("abilities", {}).items()))
    if s.get("skills"):
        print("  Skills: " + "、".join(s["skills"]))


def _do_check(ruleset, state, ctx, pc, line: str) -> None:
    parts = line.split()[1:]
    if not parts:
        print("  usage: /check ABILITY [TN] [SKILL]")
        return
    ability = parts[0].upper()
    tn = None
    skill = None
    for p in parts[1:]:
        if p.isdigit():
            tn = int(p)
        else:
            skill = p
    result = ctx.ruleset.resolve_check(
        state,
        CheckRequest(actor_id=pc.id, ability=ability, skill=skill, target_number=tn,
                     description=f"{pc.name} attempts a {ability} check"),
    )
    # Log it through the event log so it prints consistently.
    from sandcastlegm.core.events import Event
    ctx.log.append(Event(type=EventType.ROLL, text=result.describe(), data=result.to_dict()))


def _do_export(state, line: str) -> None:
    parts = line.split()
    if len(parts) < 3:
        print("  usage: /export VTT PATH   (VTT = cocofolia | udonarium)")
        return
    from sandcastlegm.vtt import get_adapter
    adapter = get_adapter(parts[1])
    payload = adapter.export_session(state)
    path = parts[2]
    if isinstance(payload, bytes):
        with open(path, "wb") as f:
            f.write(payload)
    else:
        import json
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"  exported to {path}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sandcastlegm", description="AI Game Master for tabletop RPGs.")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("rulesets", help="list installed rulesets").set_defaults(func=cmd_rulesets)

    play = sub.add_parser("play", help="play a local session")
    play.add_argument("--ruleset", default="sandcastle")
    play.add_argument("--title", default="A Sandcastle Adventure")
    play.set_defaults(func=cmd_play)

    serve = sub.add_parser("serve", help="run the multiplayer server")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.set_defaults(func=cmd_serve)

    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        # Default to play for a bare invocation.
        args = parser.parse_args((argv or []) + ["play"])
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
