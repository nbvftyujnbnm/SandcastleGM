# SandcastleGM

An **AI Game Master for tabletop RPGs**. It does more than chat: it generates and
tracks scenes, manages a tactical map with tokens, resolves dice mechanics
through the actual rules, voices NPCs, and runs encounters — for a group of
players, not just one.

It ships with the open-source **[Sandcastle](https://www.sandcastletrpg.com/)**
ruleset as the reference system, and is built around a **ruleset "patch"
interface** so other open systems can be dropped in without touching the engine.
Multiplayer happens either through the built-in session server or by exporting
state into virtual tabletops your group already uses — **Udonarium** and
**Cocofolia**.

> Status: **0.1 foundation.** The core engine, Sandcastle ruleset, dice
> resolution, scene/map/token state, the AI GM tool loop, VTT exporters, the
> multiplayer server, and a local play CLI are all implemented and tested. The
> AI GM is vendor-neutral via a provider abstraction (OpenRouter by default,
> Anthropic supported) and degrades to a deterministic referee when no API key
> is present, so the whole system is runnable offline.

---

## Why it's built this way

Three requirements shaped the architecture:

1. **More than text.** A GM that only talks can't run a battle map or keep the
   dice honest. So scenes, a tactical grid, tokens, characters, and initiative
   are first-class state — and the AI changes them through **tools**, never by
   improvising. Narration is prose; everything mechanical is a tool call against
   the authoritative rules engine.

2. **Many players.** Rather than reinvent a virtual tabletop, SandcastleGM keeps
   one shared, serialisable game state and meets groups where they are: a live
   **WebSocket session server**, plus **exporters** to Udonarium and Cocofolia.

3. **Many systems, via patches.** The engine, AI orchestration, map, and VTT
   layers never hard-code Sandcastle. A `Ruleset` object is the only thing that
   knows a game's dice, character sheet, and rules text. Adding a system
   (copyright permitting, so realistically open ones) is *writing a patch*:
   subclass `Ruleset`, register it, done.

```
            players  ──ws──►  server (rooms)  ─────┐
            CLI      ───────►  AIGameMaster  ──────┤
                                   │  tools         ▼
   ┌───────────────┐          ┌─────────────┐   ┌─────────────────┐
   │   Ruleset     │◄────────►│  core state │──►│  VTT adapters   │
   │  ("patch")    │  resolve │ scene / map │   │ Udonarium /     │
   │ dice+rules+   │  checks  │ tokens /    │   │ Cocofolia       │
   │ knowledge     │          │ characters  │   └─────────────────┘
   └───────────────┘          └─────────────┘
```

## Layout

| Module | What it is | Depends on |
|---|---|---|
| `sandcastlegm.core` | Dice engine, game state (scenes, maps, tokens, characters, turn order), event log | nothing |
| `sandcastlegm.rulesets` | The `Ruleset` patch interface, a registry, and the Sandcastle implementation | core |
| `sandcastlegm.gm` | The AI Game Master: vendor-neutral tool-use loop, tool surface, prompt assembly, and LLM providers (OpenRouter / Anthropic) | core, rulesets, `openai`* |
| `sandcastlegm.vtt` | Exporters to Udonarium (XML/zip) and Cocofolia (clipboard JSON) | core |
| `sandcastlegm.server` | Multiplayer WebSocket session server | gm, `fastapi`* |
| `sandcastlegm.cli` | Local terminal play, `serve`, and `rulesets` commands | all of the above |

\* optional extras — `core` and `rulesets` have **zero** third-party
dependencies, so the dice/rules/state engine runs anywhere.

## Install

```bash
pip install -e ".[all]"          # everything (AI GM + server)
pip install -e ".[gm]"           # AI GM, default OpenRouter backend (openai SDK)
pip install -e ".[anthropic]"    # add the Anthropic backend
pip install -e ".[dev]"          # tests
pip install -e .                 # core engine + rulesets only, no deps
```

### Choosing an LLM backend

The GM is vendor-neutral: it drives a tool-use loop against an `LLMProvider`.
Two backends ship today; new ones are a matter of implementing the interface in
`sandcastlegm/gm/providers/`.

**OpenRouter (default)** — one OpenAI-compatible endpoint for hundreds of hosted
and open-weight models. Community testing has found mid-size open models
(~27B, e.g. Gemma 3 27B) make surprisingly strong TTRPG GMs, so that's the
default model.

```bash
export OPENROUTER_API_KEY=sk-or-...
export SANDCASTLEGM_MODEL=gemma3-27b   # preset key or any OpenRouter model id
```

Run `sandcastlegm models` for the recommended list. Picks are grounded in a
community narrative-quality probe (37 open-weight models, 12 GM scenarios, a
5-judge ensemble scoring atmosphere / NPC craft / GM craft, plus rule-based
tool/structure compliance). Because this GM is *agentic* — it chains real tool
calls for dice, HP and initiative — tool-call compliance is weighted alongside
prose:

| Preset | Model | Why |
|---|---|---|
| `gemma3-27b` *(default)* | `google/gemma-3-27b-it` | The only model strong on **both** tool compliance and narration; locally hostable (~24GB). A 27B that matched models 15× its size. |
| `mistral-medium` | `mistralai/mistral-medium-3.1` | Highest overall narration with the most judge agreement. |
| `qwen3-next-80b` | `qwen/qwen3-next-80b-a3b-instruct` | Best raw prose, looser tool discipline. |
| `mistral-small` | `mistralai/mistral-small-3.2-24b-instruct` | Safest floor — zero structural failures in the sweep. |
| `ministral-8b` | `mistralai/ministral-8b-2512` | Budget pick, strong for 8B (directional). |

Findings that shaped the architecture: *the model narrates, it doesn't
calculate* (dice/HP/initiative are tools and state, never model arithmetic), and
small models drift after several chained tool calls — so the standing prompt is
kept lean (rulebook opt-in, compact state snapshot per turn).

**Anthropic (Claude)**:

```bash
export SANDCASTLEGM_PROVIDER=anthropic
export ANTHROPIC_API_KEY=sk-ant-...
export SANDCASTLEGM_MODEL=claude-opus-4-8
```

Leave `SANDCASTLEGM_PROVIDER` unset to auto-detect from whichever key is present
(OpenRouter preferred). The full rulebook is sent to the model only when
`SANDCASTLEGM_INCLUDE_RULEBOOK=true` (it needs a large context window); otherwise
the always-on ruleset guidance digest carries the core rules. See `.env.example`.

## Play locally

```bash
sandcastlegm rulesets          # list installed systems
sandcastlegm play              # start a session in your terminal
```

In the play loop you talk to the GM in plain text. Slash commands give you
direct control of the dice and state (and are all you need in referee mode):

```
/check STR 11 体術     roll a STR check at TN 11 applying the 体術 skill
/roll 2d6+1            roll arbitrary dice
/sheet                 your character sheet
/state                 current scene, characters, and ASCII map
/export cocofolia party.json
/export udonarium room.zip
```

## Run multiplayer

```bash
sandcastlegm serve --host 0.0.0.0 --port 8765
```

REST + WebSocket surface:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/rulesets` | installed systems |
| `POST` | `/sessions` | create a room (`{"ruleset_id": "sandcastle", "title": "..."}`) |
| `GET` | `/sessions/{id}` | full game state |
| `GET` | `/sessions/{id}/events` | event log (story so far) |
| `POST` | `/sessions/{id}/characters` | add a player character |
| `GET` | `/sessions/{id}/export/{cocofolia\|udonarium}` | download a VTT package |
| `WS` | `/sessions/{id}/ws` | live play: send `{"type":"action","text":"...","actor_id":"..."}`, receive every event |

Each connected player receives the backlog on join and every subsequent event
live, so a whole group shares one AI-run table.

## Virtual-tabletop integration

- **Cocofolia** — `CocofoliaAdapter` emits the clipboard JSON Cocofolia imports:
  a character piece with an HP status bar, the six abilities as params, and a
  chat palette of ready-to-roll `3d6+{ability}` commands.
- **Udonarium** — `UdonariumAdapter` emits Udonarium's XML objects
  (`<character>`, `<game-table>`) and bundles a session into a room-style zip,
  converting grid cells to Udonarium's pixel space.

The built-in server and the VTT exporters are interchangeable consumers of the
same state, so a group can use whichever fits.

## Adding a new system (writing a patch)

Supporting another (open-source) system means implementing the `Ruleset`
interface and registering it — nothing in the engine changes.

```python
from sandcastlegm.rulesets.base import Ruleset, AbilityDef, CheckRequest, CheckResult
from sandcastlegm.rulesets.registry import register
from sandcastlegm.core.state import Character

@register
class MySystem(Ruleset):
    id = "mysystem"
    name = "My Open System"

    def ability_definitions(self): ...
    def new_character(self, name, **kw) -> Character: ...
    def resolve_check(self, state, request: CheckRequest) -> CheckResult: ...
    def knowledge_text(self) -> str: ...     # rules corpus the AI GM reads
    def gm_guidance(self) -> str: ...        # tone + idioms for the system
```

A ruleset owns exactly three things: **mechanics** (how a check resolves, what a
blank character looks like), **knowledge** (the rules text the AI references to
adjudicate fairly), and **voice** (system-specific GM guidance). Third-party
patches can ship as separate packages and advertise a `sandcastlegm.rulesets`
entry point; `registry.discover_plugins()` loads them at startup so they appear
alongside the built-ins.

See `sandcastlegm/rulesets/sandcastle/` for a complete worked example.

## How the AI GM stays honest

- **Dice are tools, not prose.** The model calls `roll_check` / `roll_dice`; the
  ruleset rolls and decides success. The model never writes a result itself.
- **State is tools, not memory.** Scenes, maps, tokens, HP, and initiative
  change only through tools that mutate the shared state and log an event.
- **The rules are context.** A compact ruleset guidance digest (core mechanic,
  abilities, skills, difficulty scale) is always in the system prompt; the full
  rulebook can be inlined for large-context models via
  `SANDCASTLEGM_INCLUDE_RULEBOOK=true`.
- **It degrades gracefully.** With no provider/API key it runs as a referee:
  state and dice still work via commands; only narration is off.

## Develop

```bash
pip install -e ".[dev]"
pytest
```

## License

MIT. The Sandcastle TRPG ruleset and its rulebook are the property of their
authors and distributed under their own open license; this project bundles the
Japanese rulebook text as the GM's reference knowledge base.
