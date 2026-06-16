"""Run the narrative probe against a model and aggregate the scores.

The runner is decoupled from any SDK: it takes a ``chat`` callable
``(system, user) -> str`` for the model under test and an optional ``judge_chat``
callable for the LLM judge, so it is unit-testable with fakes. The OpenRouter
factory builds those callables from the ``openai`` SDK for real runs.

Like the probe it's modelled on, scoring is narration-only (one GM turn per
scenario, no tool calls) to isolate writing quality from tool plumbing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from sandcastlegm.probe import scoring
from sandcastlegm.probe.scenarios import PROBE_SYSTEM, SCENARIOS, Scenario

ChatFn = Callable[[str, str], str]


@dataclass
class ScenarioResult:
    key: str
    response: str
    auto: dict[str, Any]
    judge: dict[str, float] | None = None


@dataclass
class ModelReport:
    model: str
    results: list[ScenarioResult] = field(default_factory=list)

    @property
    def auto_counts(self) -> dict[str, int]:
        counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
        for r in self.results:
            counts[r.auto["verdict"]] += 1
        return counts

    @property
    def judge_means(self) -> dict[str, float]:
        dims = ("atmosphere", "npc_craft", "gm_craft")
        scored = [r.judge for r in self.results if r.judge]
        if not scored:
            return {}
        means = {d: sum(j[d] for j in scored) / len(scored) for d in dims}
        means["overall"] = sum(means[d] for d in dims) / 3
        return means

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "auto_counts": self.auto_counts,
            "judge_means": {k: round(v, 3) for k, v in self.judge_means.items()},
            "results": [
                {"key": r.key, "response": r.response, "auto": r.auto, "judge": r.judge}
                for r in self.results
            ],
        }


class ProbeRunner:
    def __init__(
        self,
        chat: ChatFn,
        judge_chat: ChatFn | None = None,
        scenarios: list[Scenario] | None = None,
    ) -> None:
        self.chat = chat
        self.judge_chat = judge_chat
        self.scenarios = scenarios or SCENARIOS

    def run_scenario(self, scenario: Scenario) -> ScenarioResult:
        response = self.chat(PROBE_SYSTEM, scenario.instruction).strip()
        auto = scoring.auto_score(response, scenario).to_dict()
        judge = None
        if self.judge_chat is not None:
            raw = self.judge_chat(
                scoring.JUDGE_SYSTEM, scoring.build_judge_prompt(scenario, response)
            )
            judge = scoring.parse_judge(raw)
        return ScenarioResult(key=scenario.key, response=response, auto=auto, judge=judge)

    def run(self, model: str = "model") -> ModelReport:
        report = ModelReport(model=model)
        for scenario in self.scenarios:
            report.results.append(self.run_scenario(scenario))
        return report


# --- OpenRouter chat factory --------------------------------------------------
def build_openrouter_chat(
    model: str,
    *,
    temperature: float = 0.8,
    max_tokens: int = 600,
    api_key: str | None = None,
    base_url: str = "https://openrouter.ai/api/v1",
    client: Any | None = None,
) -> ChatFn:
    """Build a ``(system, user) -> str`` chat callable backed by OpenRouter."""
    if client is None:
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is required to run the probe")
        from openai import OpenAI

        client = OpenAI(api_key=key, base_url=base_url)

    def chat(system: str, user: str) -> str:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    return chat


def summarize(reports: list[ModelReport]) -> str:
    """A compact ranking table over one or more model reports."""
    rows = []
    for rep in reports:
        c = rep.auto_counts
        m = rep.judge_means
        rows.append(
            (
                m.get("overall", 0.0),
                f"{rep.model:<34} P:{c['PASS']} W:{c['WARN']} F:{c['FAIL']}  "
                f"atm {m.get('atmosphere', 0):.2f}  npc {m.get('npc_craft', 0):.2f}  "
                f"gm {m.get('gm_craft', 0):.2f}  overall {m.get('overall', 0):.2f}",
            )
        )
    rows.sort(key=lambda r: r[0], reverse=True)
    header = "Narrative probe results (sorted by judge overall):\n"
    return header + "\n".join(line for _, line in rows)
