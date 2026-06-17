"""OpenRouter provider (the default backend).

OpenRouter exposes one OpenAI-compatible endpoint that routes to hundreds of
models — hosted frontier models and open-weight ones alike — so a group can pick
whatever runs a good table for them. Community testing has found mid-size open
models (around 27B, e.g. Gemma 3 27B) punch well above their weight as TTRPG
GMs, which is why that is the default model here; override it freely.

Tool calling uses the standard OpenAI function-call shape, so the GM tool
schemas pass straight through as JSON Schema — no per-model schema massaging.
"""

from __future__ import annotations

import json
import os
from typing import Any

from sandcastlegm.gm.models import DEFAULT_OPENROUTER_MODEL, resolve_model
from sandcastlegm.gm.providers.base import (
    LLMProvider,
    LLMResponse,
    LLMToolCall,
    ToolResult,
)

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = DEFAULT_OPENROUTER_MODEL


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        *,
        temperature: float = 0.8,
        max_tokens: int = 2048,
        base_url: str = OPENROUTER_BASE_URL,
        extra_headers: dict[str, str] | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = resolve_model(
            model or os.environ.get("SANDCASTLEGM_MODEL") or DEFAULT_MODEL
        )
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._messages: list[dict[str, Any]] = []
        self._client = (
            client if client is not None else self._make_client(api_key, base_url, extra_headers)
        )

    def _make_client(
        self, api_key: str | None, base_url: str, extra_headers: dict[str, str] | None
    ) -> Any | None:
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        # OpenRouter uses these optional headers for attribution/ranking.
        headers: dict[str, str] = {}
        if site := os.environ.get("OPENROUTER_SITE_URL"):
            headers["HTTP-Referer"] = site
        if app := os.environ.get("OPENROUTER_APP_NAME", "SandcastleGM"):
            headers["X-Title"] = app
        if extra_headers:
            headers.update(extra_headers)
        # Point at any OpenAI-compatible endpoint (e.g. a local Ollama/LM Studio
        # server) for a genuinely free path. For local servers OPENROUTER_API_KEY
        # can be any non-empty placeholder.
        base_url = os.environ.get("OPENROUTER_BASE_URL", base_url)
        return OpenAI(api_key=key, base_url=base_url, default_headers=headers or None)

    @property
    def available(self) -> bool:
        return self._client is not None

    def add_user(self, text: str) -> None:
        self._messages.append({"role": "user", "content": text})

    def add_tool_results(self, results: list[ToolResult]) -> None:
        for r in results:
            self._messages.append(
                {"role": "tool", "tool_call_id": r.id, "content": r.content}
            )

    def generate(self, system: str, tools: list[dict[str, Any]]) -> LLMResponse:
        oai_tools = [
            {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t["input_schema"],
                },
            }
            for t in tools
        ]
        messages = [{"role": "system", "content": system}, *self._messages]
        response = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=oai_tools,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        msg = response.choices[0].message

        assistant: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        calls: list[LLMToolCall] = []
        if getattr(msg, "tool_calls", None):
            assistant["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                }
                for tc in msg.tool_calls
            ]
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append(LLMToolCall(id=tc.id, name=tc.function.name, args=args))

        self._messages.append(assistant)
        return LLMResponse(text=msg.content or "", tool_calls=calls)
