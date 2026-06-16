"""Recommended models for running the GM, with short presets.

Grounded in a community narrative-quality probe that scored open-weight models
as TTRPG GMs across 12 scenarios with a 5-judge ensemble (atmosphere, NPC craft,
GM craft) plus rule-based tool/structure compliance (auto Pass/Warn/Fail).

Two findings drive the picks below. First, for an *agentic* GM like this one —
which chains real tool calls (dice, HP, initiative) before and during narration
— tool-call compliance matters as much as prose. Gemma 3 27B was the only model
strong on both axes (best auto-compliance and high narration scores), so it is
the default. Second, bigger is not better for narration: a 27B beat a 405B.

Pick a model with the ``key`` (resolved to the full OpenRouter id) or pass any
OpenRouter model id directly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelRec:
    key: str
    id: str
    score: float  # overall judge score from the 37-model v2 sweep
    note: str


# Ordered best-fit-first for this agentic, tool-heavy GM (compliance weighted).
RECOMMENDED_OPENROUTER_MODELS: list[ModelRec] = [
    ModelRec(
        "gemma3-27b", "google/gemma-3-27b-it", 4.75,
        "Default. The only model strong on BOTH tool-call compliance and "
        "narration; best auto-compliance in the sweep. Locally hostable (~24GB).",
    ),
    ModelRec(
        "mistral-medium", "mistralai/mistral-medium-3.1", 4.80,
        "Top overall narration with the highest judge agreement (most reliable "
        "high score). Excellent compliance.",
    ),
    ModelRec(
        "qwen3-next-80b", "qwen/qwen3-next-80b-a3b-instruct", 4.88,
        "Highest raw narration scores, but weaker structural/tool compliance — "
        "best when prose matters more than tight tool discipline.",
    ),
    ModelRec(
        "mistral-small", "mistralai/mistral-small-3.2-24b-instruct", 4.61,
        "Safest floor: zero structural failures across the whole sweep.",
    ),
    ModelRec(
        "nemotron-nano-30b", "nvidia/nemotron-3-nano-30b-a3b", 4.68,
        "Best atmosphere / scene-painting; thinner NPC dialogue.",
    ),
    ModelRec(
        "ministral-8b", "mistralai/ministral-8b-2512", 4.76,
        "Budget pick — surprisingly strong at 8B (directional; low judge "
        "agreement, so verify on your own table).",
    ),
    ModelRec(
        "cydonia-24b", "thedrummer/cydonia-24b-v4.1", 4.48,
        "Best of the roleplay finetunes; evocative voice with decent discipline.",
    ),
]

#: default OpenRouter model id (see module docstring for why)
DEFAULT_OPENROUTER_MODEL = RECOMMENDED_OPENROUTER_MODELS[0].id

_PRESETS: dict[str, str] = {m.key: m.id for m in RECOMMENDED_OPENROUTER_MODELS}


def resolve_model(name: str | None) -> str | None:
    """Map a preset key to its full model id; pass anything else through."""
    if name is None:
        return None
    return _PRESETS.get(name, name)
