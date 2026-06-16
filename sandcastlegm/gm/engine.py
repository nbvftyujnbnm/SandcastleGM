"""The AI Game Master engine.

:class:`AIGameMaster` runs a vendor-neutral tool-use loop against an
:class:`~sandcastlegm.gm.providers.base.LLMProvider`: it sends the player's
message plus a fresh snapshot of the game state, lets the model narrate and call
the GM tools (which mutate state and append events), feeds the tool results back,
and repeats until the model stops calling tools. Dice and state changes go
through tools, so the mechanics stay authoritative regardless of which model
runs the table.

With no provider configured (no API key, or the SDK missing) the engine runs in
**referee** mode: state and dice still work via the tools/CLI; only narration is
off. This keeps the whole system runnable and testable offline.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from sandcastlegm.core.events import Event, EventLog, EventType
from sandcastlegm.core.state import GameState
from sandcastlegm.gm import prompts, tools
from sandcastlegm.gm.providers import LLMProvider, ToolResult, make_default_provider
from sandcastlegm.rulesets.base import Ruleset

MAX_TOOL_ITERATIONS = 12

# Sentinel so `provider=None` can explicitly force referee mode, while the
# default ("auto") builds a provider from the environment.
_AUTO = object()


@dataclass
class GMTurn:
    """The result of one player turn."""

    narration: str
    events: list[Event] = field(default_factory=list)
    degraded: bool = False


class AIGameMaster:
    def __init__(
        self,
        ruleset: Ruleset,
        state: GameState,
        log: EventLog | None = None,
        *,
        provider: LLMProvider | None | object = _AUTO,
        model: str | None = None,
        include_rulebook: bool | None = None,
        max_iterations: int = MAX_TOOL_ITERATIONS,
    ) -> None:
        self.ruleset = ruleset
        self.state = state
        self.log = log or EventLog()
        self.max_iterations = max_iterations
        self.provider: LLMProvider | None = (
            make_default_provider(model) if provider is _AUTO else provider  # type: ignore[assignment]
        )

        if include_rulebook is None:
            include_rulebook = os.environ.get(
                "SANDCASTLEGM_INCLUDE_RULEBOOK", ""
            ).lower() in ("1", "true", "yes")
        self._static_system = prompts.build_static_system(
            ruleset, include_rulebook=include_rulebook
        )

    @property
    def ctx(self) -> tools.GMContext:
        return tools.GMContext(ruleset=self.ruleset, state=self.state, log=self.log)

    @property
    def available(self) -> bool:
        """True when an LLM GM is wired up; False means referee/manual mode."""
        return self.provider is not None and self.provider.available

    # --- main entry point -----------------------------------------------------
    def turn(self, player_message: str, actor_id: str | None = None) -> GMTurn:
        """Process one player message and return the GM's narration + events."""
        before = len(self.log.events)
        self.log.append(
            Event(type=EventType.PLAYER_ACTION, text=player_message, actor=actor_id)
        )

        if not self.available:
            return GMTurn(
                narration=(
                    "[AI GM unavailable — running as a rules referee. Set an API key "
                    "(OPENROUTER_API_KEY) for narration; you can still roll and manage "
                    "state via commands.]"
                ),
                events=self.log.events[before:],
                degraded=True,
            )

        narration = self._run_llm_turn(player_message, actor_id)
        if narration:
            self.log.append(Event(type=EventType.NARRATION, text=narration))
        return GMTurn(narration=narration, events=self.log.events[before:])

    # --- the vendor-neutral tool-use loop ------------------------------------
    def _run_llm_turn(self, player_message: str, actor_id: str | None) -> str:
        assert self.provider is not None
        snapshot = prompts.render_state_snapshot(self.state)
        actor_note = f"(acting as {actor_id})" if actor_id else ""
        self.provider.add_user(f"{snapshot}\n\n{actor_note}\n{player_message}".strip())

        narration_parts: list[str] = []
        for _ in range(self.max_iterations):
            response = self.provider.generate(self._static_system, tools.TOOL_SPECS)
            if response.text:
                narration_parts.append(response.text)

            if not response.tool_calls:
                break

            results = [
                ToolResult(
                    id=call.id,
                    name=call.name,
                    content=tools.execute_tool(self.ctx, call.name, call.args),
                )
                for call in response.tool_calls
            ]
            self.provider.add_tool_results(results)

        return "\n\n".join(p.strip() for p in narration_parts if p.strip())
