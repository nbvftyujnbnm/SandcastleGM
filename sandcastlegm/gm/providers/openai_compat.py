"""Shared base for OpenAI-compatible chat backends.

Several providers speak the OpenAI Chat Completions wire format — OpenRouter and
Google's Gemini compatibility endpoint among them — so the tool-use translation
and message-history handling live here once. Concrete providers subclass this and
override only what differs: the default base URL, which env vars hold the key,
the default model, optional attribution headers, and model-id resolution.
"""

from __future__ import annotations

import json
import os
from typing import Any

from sandcastlegm.gm.providers.base import (
    LLMProvider,
    LLMResponse,
    LLMToolCall,
    ToolResult,
)


class OpenAICompatibleProvider(LLMProvider):
    name = "openai-compatible"
    default_model = "gpt-4o-mini"
    base_url = "https://api.openai.com/v1"
    base_url_env: str | None = None  # env var that can override base_url
    api_key_envs: tuple[str, ...] = ("OPENAI_API_KEY",)

    def __init__(
        self,
        model: str | None = None,
        api_key: str | None = None,
        *,
        temperature: float = 0.8,
        max_tokens: int = 2048,
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
        client: Any | None = None,
    ) -> None:
        self.model = self._resolve_model(
            model or os.environ.get("SANDCASTLEGM_MODEL") or self.default_model
        )
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._messages: list[dict[str, Any]] = []
        self._client = (
            client if client is not None else self._make_client(api_key, base_url, extra_headers)
        )

    # --- hooks subclasses may override ---------------------------------------
    def _resolve_model(self, name: str) -> str:
        return name

    def _get_api_key(self, api_key: str | None) -> str | None:
        if api_key:
            return api_key
        for env in self.api_key_envs:
            if value := os.environ.get(env):
                return value
        return None

    def _default_headers(self) -> dict[str, str]:
        return {}

    # --- client setup ---------------------------------------------------------
    def _make_client(
        self, api_key: str | None, base_url: str | None, extra_headers: dict[str, str] | None
    ) -> Any | None:
        key = self._get_api_key(api_key)
        if not key:
            return None
        try:
            from openai import OpenAI
        except ImportError:
            return None
        resolved_base = base_url or (
            os.environ.get(self.base_url_env) if self.base_url_env else None
        ) or self.base_url
        headers = self._default_headers()
        if extra_headers:
            headers.update(extra_headers)
        return OpenAI(api_key=key, base_url=resolved_base, default_headers=headers or None)

    # --- LLMProvider ----------------------------------------------------------
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
