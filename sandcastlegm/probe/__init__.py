"""Narrative-quality probe: score models as Sandcastle GMs.

Sends each model a fixed set of GM scenarios grounded in a shared setting, then
scores the prose two ways — fast rule-based auto-checks (PASS/WARN/FAIL) and an
LLM judge (atmosphere / NPC craft / GM craft, 1–5). Run it with
``sandcastlegm probe`` to pick a model for your own table and hardware.
"""

from sandcastlegm.probe.runner import (
    ModelReport,
    ProbeRunner,
    ScenarioResult,
    build_openrouter_chat,
    summarize,
)
from sandcastlegm.probe.scenarios import SCENARIOS, Scenario
from sandcastlegm.probe.scoring import AutoScore, auto_score

__all__ = [
    "ModelReport",
    "ProbeRunner",
    "ScenarioResult",
    "build_openrouter_chat",
    "summarize",
    "SCENARIOS",
    "Scenario",
    "AutoScore",
    "auto_score",
]
