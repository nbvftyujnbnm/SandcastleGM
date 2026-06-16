"""Anthropic (Claude) provider.

Keeps Claude available as a backend alongside OpenRouter. It stores the native
Anthropic message history — appending the raw response content blocks verbatim —
so adaptive-thinking blocks round-trip correctly, and marks the (large) system
prompt for prompt caching.
"""

from __future__ import annotations

import os
from typing import Any

from sandcastlegm.gm.providers.base import (
    LLMProvider,
    LLMResponse,
    LLMToolCall,
    ToolResult,
)

DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_EFFORT = "medium"


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        *,
        effort: str | None = None,
        max_tokens: int = 4096,
        client: Any | None = None,
    ) -> None:
        self.model = model or os.environ.get("SANDCASTLEGM_MODEL") or DEFAULT_MODEL
        self.effort = effort or os.environ.get("SANDCASTLEGM_EFFORT", DEFAULT_EFFORT)
        self.max_tokens = max_tokens
        self._messages: list[dict[str, Any]] = []
        self._client = client if client is not None else self._make_client(api_key)

    def _make_client(self, api_key: str | None) -> Any | None:
        if not (api_key or os.environ.get("ANTHROPIC_API_KEY")):
            return None
        try:
            import anthropic
        except ImportError:
            return None
        return anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    @property
    def available(self) -> bool:
        return self._client is not None

    def add_user(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})

    def add_tool_results(self, results: list[ToolResult]) -> None:
        self._messages.append(
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": r.id, "content": r.content}
                    for r in results
                ],
            }
        )

    def generate(self, system: str, tools: list[dict[str, Any]]) -> LLMResponse:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
            tools=tools,  # Anthropic consumes the input_schema shape directly.
            thinking={"type": "adaptive"},
            output_config={"effort": self.effort},
            messages=self._messages,
        )

        text_parts: list[str] = []
        calls: list[LLMToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append(LLMToolCall(id=block.id, name=block.name, args=dict(block.input)))

        # Append the raw blocks so thinking signatures survive the round-trip.
        self._messages.append({"role": "assistant", "content": response.content})
        return LLMResponse(text="\n".join(text_parts), tool_calls=calls)
