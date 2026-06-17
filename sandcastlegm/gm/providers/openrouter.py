"""OpenRouter provider.

OpenRouter exposes one OpenAI-compatible endpoint that routes to hundreds of
models — hosted frontier models and open-weight ones alike — so a group can pick
whatever runs a good table for them. Community testing has found mid-size open
models (around 27B, e.g. Gemma 3 27B) punch well above their weight as TTRPG
GMs, which is why that is the default model here; override it freely.

``OPENROUTER_BASE_URL`` can repoint the same client at any other OpenAI-compatible
server (e.g. a local Ollama / LM Studio instance) for a no-cost path.
"""

from __future__ import annotations

import os

from sandcastlegm.gm.models import DEFAULT_OPENROUTER_MODEL, resolve_model
from sandcastlegm.gm.providers.openai_compat import OpenAICompatibleProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_MODEL = DEFAULT_OPENROUTER_MODEL


class OpenRouterProvider(OpenAICompatibleProvider):
    name = "openrouter"
    default_model = DEFAULT_MODEL
    base_url = OPENROUTER_BASE_URL
    base_url_env = "OPENROUTER_BASE_URL"
    api_key_envs = ("OPENROUTER_API_KEY",)

    def _resolve_model(self, name: str) -> str:
        return resolve_model(name) or name

    def _default_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if site := os.environ.get("OPENROUTER_SITE_URL"):
            headers["HTTP-Referer"] = site
        if app := os.environ.get("OPENROUTER_APP_NAME", "SandcastleGM"):
            headers["X-Title"] = app
        return headers
