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
import json
import os
import pathlib
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
  /save [PATH]           save the session (resume later with --load PATH)
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


def cmd_models(_: argparse.Namespace) -> int:
    from sandcastlegm.gm.models import RECOMMENDED_OPENROUTER_MODELS

    print("Recommended OpenRouter models (best-fit-first for this agentic GM):\n")
    for m in RECOMMENDED_OPENROUTER_MODELS:
        print(f"  {m.key:<18} {m.id}")
        print(f"  {'':<18} score {m.score}  — {m.note}\n")
    print("Use with: sandcastlegm play --model <key|full-model-id>")
    print("or set SANDCASTLEGM_MODEL in your environment.")
    print(
        "\nFree tier: add ':free' for OpenRouter's free variant "
        "(e.g. gemma3-27b:free). Free models are rate-limited and not available "
        "for every model."
    )
    return 0


def cmd_probe(args: argparse.Namespace) -> int:
    try:
        import openai  # noqa: F401
    except ImportError:
        print("The probe needs the OpenRouter backend: pip install 'sandcastlegm[gm]'", file=sys.stderr)
        return 1
    if not os.environ.get("OPENROUTER_API_KEY"):
        print("Set OPENROUTER_API_KEY to run the probe.", file=sys.stderr)
        return 1

    from sandcastlegm.gm.models import resolve_model
    from sandcastlegm.probe import ProbeRunner, build_openrouter_chat, summarize

    models = [m.strip() for m in (args.models.split(",") if args.models else [args.model]) if m.strip()]
    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    judge_chat = None
    if not args.no_judge:
        judge_chat = build_openrouter_chat(
            resolve_model(args.judge), temperature=0.0, max_tokens=args.judge_max_tokens
        )

    reports = []
    judge_errors = 0
    for m in models:
        full = resolve_model(m)
        print(f"Running probe: {full} ...")
        runner = ProbeRunner(build_openrouter_chat(full), judge_chat)
        try:
            report = runner.run(model=full)
        except Exception as exc:  # noqa: BLE001 - report and continue to next model
            print(f"  failed: {type(exc).__name__}: {exc}", file=sys.stderr)
            if "credit" in str(exc).lower() or "402" in str(exc):
                print(
                    "  hint: OpenRouter requires a one-time credit purchase (~$10 "
                    "lifetime) before its ':free' models work; new accounts get a "
                    "402 like this. Either add credits, point OPENROUTER_BASE_URL "
                    "at a local OpenAI-compatible server (Ollama/LM Studio), or use "
                    "a paid model.",
                    file=sys.stderr,
                )
            continue
        reports.append(report)
        judge_errors += runner.judge_errors
        if runner.judge_errors:
            print(f"  note: {runner.judge_errors} judge call(s) failed — those scores omitted.")
        (out_dir / f"{full.replace('/', '_')}.json").write_text(
            json.dumps(report.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    if reports:
        print("\n" + summarize(reports))
        print(f"\nFull results written to {out_dir}/")
    if judge_errors:
        print(
            "\nThe judge model failed on some calls. The default judge "
            f"({args.judge}) is a paid model — for a free-only account, pass a "
            "free judge (e.g. --judge openai/gpt-oss-20b:free) or --no-judge to "
            "rely on the rule-based auto-scores.",
            file=sys.stderr,
        )
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

    log = EventLog()
    if getattr(args, "load", None):
        from sandcastlegm.core.persistence import load_session
        loaded_state, loaded_log = load_session(args.load)
        state = loaded_state
        log.load(loaded_log.to_list())
        ruleset = registry.create(state.ruleset_id, rng=random.Random())
        print(f"(resumed {args.load}: {len(log.events)} events, {len(state.characters)} characters)")
    else:
        ruleset = registry.create(args.ruleset, rng=random.Random())
        state = GameState(ruleset_id=args.ruleset, title=args.title)

    log.subscribe(_print_event)
    gm = AIGameMaster(ruleset, state, log, model=getattr(args, "model", None))

    # Use an existing PC when resuming; otherwise quick character creation.
    pcs = state.player_characters()
    if pcs:
        pc = pcs[0]
    else:
        name = input("Your character's name [Hero]: ").strip() or "Hero"
        pc = ruleset.new_character(name, controller="local")
        state.add_character(pc)

    print()
    print(f"=== {state.title} — {ruleset.name} ===")
    provider_name = gm.provider.name if gm.provider is not None else "none"
    status = f"on ({provider_name}: {gm.provider.model})" if gm.available else (
        "OFF (referee mode — set OPENROUTER_API_KEY for narration)"
    )
    print(f"AI GM: {status}")
    print(HELP)
    if gm.available and state.current_scene is None:
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
        elif line.startswith("/save"):
            from sandcastlegm.core.persistence import save_session, save_session_to_dir
            parts = line.split(maxsplit=1)
            path = save_session(state, log, parts[1]) if len(parts) > 1 else save_session_to_dir(state, log)
            print(f"  saved to {path}  (resume: sandcastlegm play --load {path})")
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
    sub.add_parser("models", help="list recommended OpenRouter models").set_defaults(func=cmd_models)

    play = sub.add_parser("play", help="play a local session")
    play.add_argument("--ruleset", default="sandcastle")
    play.add_argument("--title", default="A Sandcastle Adventure")
    play.add_argument("--model", default=None, help="OpenRouter model id or preset key (see `models`)")
    play.add_argument("--load", default=None, help="resume a saved session JSON (see /save)")
    play.set_defaults(func=cmd_play)

    probe = sub.add_parser("probe", help="score models as GMs (needs OPENROUTER_API_KEY)")
    probe.add_argument("--model", default="gemma3-27b", help="model preset key or id to probe")
    probe.add_argument("--models", default=None, help="comma-separated models to compare")
    probe.add_argument("--judge", default="openai/gpt-oss-20b", help="judge model id")
    probe.add_argument("--judge-max-tokens", type=int, default=300, dest="judge_max_tokens")
    probe.add_argument("--no-judge", action="store_true", help="auto-scoring only, no LLM judge")
    probe.add_argument("--out", default="probe_results", help="output directory for result JSON")
    probe.set_defaults(func=cmd_probe)

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
