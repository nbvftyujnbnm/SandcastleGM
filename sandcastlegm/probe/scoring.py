"""Scoring for the narrative probe.

Two independent signals, as in the probe this is modelled on:

* :func:`auto_score` — fast, deterministic, rule-based heuristics that catch
  whether a response follows GM conventions (sensible length, sensory detail,
  NPC dialogue where expected, a forward hook). Returns a PASS / WARN / FAIL
  verdict. No network, fully testable.
* the LLM judge (:func:`build_judge_prompt` / :func:`parse_judge`) — a model
  scores atmosphere, NPC craft, and GM craft 1–5. The judge catches whether the
  prose is actually good; the auto-scorer catches whether it's well-formed. They
  can disagree, and both are reported.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from sandcastlegm.probe.scenarios import Scenario

# Small bilingual cue lists; enough to estimate sensory grounding, not exhaustive.
_SENSORY = re.compile(
    r"\b(ash|soot|smoke|smell|scent|reek|stench|cold|warm|heat|damp|wet|dust|"
    r"glow|shadow|flicker|echo|whisper|hiss|clatter|grit|grime|rust|salt|"
    r"taste|tang|chill|sour|acrid|lantern|torch|fog|mist|grey|gray)\w*",
    re.IGNORECASE,
)
_DIALOGUE = re.compile(r"[\"“”„«»「」『』]")
_HOOK_HINT = re.compile(
    r"(\?|\byou (can|could|might|see|hear|notice|feel|realise|realize|catch)\b|"
    r"\bwhat (do|will) you\b|\bbefore you\b|…|\.\.\.)",
    re.IGNORECASE,
)
# Mechanics leaking into prose (the GM should narrate, not compute).
_DICE_LEAK = re.compile(
    r"\b(\d*d\d+|roll(ed)?|DC\b|target number|TN\b|\d+\s*(hp|damage|points))\b",
    re.IGNORECASE,
)

# Length bands (words): comfortable PASS, acceptable WARN, outside = FAIL.
PASS_MIN, PASS_MAX = 40, 220
WARN_MIN, WARN_MAX = 25, 350

Verdict = str  # "PASS" | "WARN" | "FAIL"


@dataclass
class AutoScore:
    verdict: Verdict
    word_count: int
    sensory_per_100w: float
    has_dialogue: bool
    has_hook: bool
    dice_leak: bool
    flags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "word_count": self.word_count,
            "sensory_per_100w": round(self.sensory_per_100w, 2),
            "has_dialogue": self.has_dialogue,
            "has_hook": self.has_hook,
            "dice_leak": self.dice_leak,
            "flags": list(self.flags),
        }


def auto_score(text: str, scenario: Scenario) -> AutoScore:
    words = re.findall(r"\S+", text)
    n = len(words)
    sensory = len(_SENSORY.findall(text))
    sensory_per_100w = (sensory / n * 100) if n else 0.0
    has_dialogue = bool(_DIALOGUE.search(text))
    has_hook = bool(_HOOK_HINT.search(text))
    dice_leak = bool(_DICE_LEAK.search(text))

    fails: list[str] = []
    warns: list[str] = []

    if n < WARN_MIN or n > WARN_MAX:
        fails.append("length")
    elif n < PASS_MIN or n > PASS_MAX:
        warns.append("length")

    if sensory_per_100w < 1.0:
        warns.append("thin-sensory")
    if "dialogue" in scenario.expects and not has_dialogue:
        warns.append("no-dialogue")
    if "hook" in scenario.expects and not has_hook:
        warns.append("no-hook")
    if dice_leak:
        fails.append("dice-in-prose")  # narrator computed/quoted mechanics

    verdict: Verdict = "FAIL" if fails else ("WARN" if warns else "PASS")
    return AutoScore(
        verdict=verdict,
        word_count=n,
        sensory_per_100w=sensory_per_100w,
        has_dialogue=has_dialogue,
        has_hook=has_hook,
        dice_leak=dice_leak,
        flags=fails + warns,
    )


JUDGE_SYSTEM = (
    "You are a strict but fair evaluator of tabletop RPG game-master narration. "
    "Score the response on three dimensions, each an integer 1-5:\n"
    "- atmosphere: sensory detail, tone, immersion\n"
    "- npc_craft: distinctiveness and characterisation of any NPC voice\n"
    "- gm_craft: pacing, forward momentum, scene management\n"
    "Reply with ONLY a JSON object: "
    '{"atmosphere": n, "npc_craft": n, "gm_craft": n}. No other text.'
)


def build_judge_prompt(scenario: Scenario, response: str) -> str:
    return (
        f"Scenario asked of the GM: {scenario.instruction}\n\n"
        f"GM response:\n\"\"\"\n{response}\n\"\"\"\n\n"
        "Score it now as JSON."
    )


def parse_judge(text: str) -> dict[str, float] | None:
    """Extract the judge's JSON scores, tolerating surrounding text."""
    match = re.search(r"\{.*?\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    out: dict[str, float] = {}
    for dim in ("atmosphere", "npc_craft", "gm_craft"):
        try:
            out[dim] = float(data[dim])
        except (KeyError, TypeError, ValueError):
            return None
    return out
