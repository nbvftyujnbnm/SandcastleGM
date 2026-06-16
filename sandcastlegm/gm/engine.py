"""The AI Game Master engine.

:class:`AIGameMaster` runs the Anthropic tool-use loop: it sends the player's
message plus a fresh snapshot of the game state, lets Claude narrate and call the
GM tools (which mutate state and append events), and feeds tool results back
until the turn ends. The model resolves dice through the ruleset via tools, so
the mechanics stay authoritative.

If the ``anthropic`` package or an API key is unavailable, the engine runs in a
**referee** mode: it still tracks state and logs player actions, and the tools
remain available for manual/CLI use — it just doesn't generate narration. This
keeps the whole system runnable and testable without network access.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from sandcastlegm.core.events import Event, EventLog, EventType
from sandcastlegm.core.state import GameState
from sandcastlegm.gm import prompts, tools
from sandcastlegm.rulesets.base import Ruleset

DEFAULT_MODEL = os.environ.get("SANDCASTLEGM_MODEL", "claude-opus-4-8")
DEFAULT_EFFORT = os.environ.get("SANDCASTLEGM_EFFORT", "medium")
MAX_TOOL_ITERATIONS = 12


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
        model: str = DEFAULT_MODEL,
        effort: str = DEFAULT_EFFORT,
        client: Any | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self.ruleset = ruleset
        self.state = state
        self.log = log or EventLog()
        self.model = model
        self.effort = effort
        self.max_tokens = max_tokens
        self._messages: list[dict[str, Any]] = []
        self._client = client if client is not None else self._make_client()
        self._static_system = prompts.build_static_system(ruleset)

    @property
    def ctx(self) -> tools.GMContext:
        return tools.GMContext(ruleset=self.ruleset, state=self.state, log=self.log)

    @property
    def available(self) -> bool:
        """True when an LLM GM is wired up; False means referee/manual mode."""
        return self._client is not None

    def _make_client(self) -> Any | None:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        try:
            import anthropic
        except ImportError:
            return None
        return anthropic.Anthropic()

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
                    "[AI GM unavailable — running as a rules referee. Set "
                    "ANTHROPIC_API_KEY for narration; you can still roll and manage "
                    "state via commands.]"
                ),
                events=self.log.events[before:],
                degraded=True,
            )

        narration = self._run_llm_turn(player_message, actor_id)
        if narration:
            self.log.append(Event(type=EventType.NARRATION, text=narration))
        return GMTurn(narration=narration, events=self.log.events[before:])

    # --- the Anthropic tool-use loop -----------------------------------------
    def _run_llm_turn(self, player_message: str, actor_id: str | None) -> str:
        snapshot = prompts.render_state_snapshot(self.state)
        actor_note = f"(acting as {actor_id})" if actor_id else ""
        self._messages.append(
            {
                "role": "user",
                "content": f"{snapshot}\n\n{actor_note}\n{player_message}".strip(),
            }
        )

        system = [
            {
                "type": "text",
                "text": self._static_system,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        narration_parts: list[str] = []
        for _ in range(MAX_TOOL_ITERATIONS):
            response = self._client.messages.create(
                model=self.model,
                max_tokens=self.max_tokens,
                system=system,
                tools=tools.TOOL_SPECS,
                thinking={"type": "adaptive"},
                output_config={"effort": self.effort},
                messages=self._messages,
            )

            for block in response.content:
                if block.type == "text":
                    narration_parts.append(block.text)

            self._messages.append({"role": "assistant", "content": response.content})

            if response.stop_reason != "tool_use":
                break

            tool_results = []
            for block in response.content:
                if block.type == "tool_use":
                    result = tools.execute_tool(self.ctx, block.name, dict(block.input))
                    tool_results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result,
                        }
                    )
            self._messages.append({"role": "user", "content": tool_results})

        return "\n\n".join(p.strip() for p in narration_parts if p.strip())
