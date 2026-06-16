"""LLM provider abstraction.

The GM engine is vendor-neutral: it drives a tool-use loop against an
:class:`LLMProvider` and never imports a specific SDK. Each provider owns its own
native conversation history (so quirks like Anthropic's thinking blocks or
OpenAI's tool-call message shape stay correct) and exposes three operations the
engine needs:

* :meth:`add_user` — append the player's turn,
* :meth:`generate` — call the model with the system prompt + tool schemas and
  return normalised text plus any tool calls,
* :meth:`add_tool_results` — feed the executed tool outputs back.

The default backend is OpenRouter (one OpenAI-compatible endpoint that reaches
hosted and open models alike); Anthropic is also available. New backends are a
matter of implementing this interface.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class LLMToolCall:
    """A tool the model wants to run, with arguments already parsed to a dict."""

    id: str
    name: str
    args: dict[str, Any]


@dataclass
class ToolResult:
    """The result of executing one tool call, fed back to the model."""

    id: str
    name: str
    content: str


@dataclass
class LLMResponse:
    """A normalised model turn: narration text and/or tool calls."""

    text: str = ""
    tool_calls: list[LLMToolCall] = field(default_factory=list)


class LLMProvider(ABC):
    """A model backend that maintains its own conversation history."""

    name: str = "base"
    model: str = ""

    @property
    @abstractmethod
    def available(self) -> bool:
        """True when the SDK is importable and credentials are present."""

    @abstractmethod
    def add_user(self, text: str) -> None:
        """Append a user/player message to the conversation."""

    @abstractmethod
    def generate(self, system: str, tools: list[dict[str, Any]]) -> LLMResponse:
        """Call the model and return its turn. Appends the reply to history."""

    @abstractmethod
    def add_tool_results(self, results: list[ToolResult]) -> None:
        """Append executed tool outputs so the model can continue."""
