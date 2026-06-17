"""Google Gemini provider.

Uses Gemini through Google's official OpenAI-compatible endpoint, so it reuses
the same tool-use machinery as the other backends. The key is a Google AI Studio
API key (``GEMINI_API_KEY`` or ``GOOGLE_API_KEY``) — the AI Studio free tier
needs no credit card and, unlike OpenRouter's free models, no prior purchase.

Default model is ``gemini-2.5-flash`` (fast, free-tier friendly, tool-calling);
set ``gemini-2.5-pro`` for higher quality, or any current Gemini id.
"""

from __future__ import annotations

from sandcastlegm.gm.providers.openai_compat import OpenAICompatibleProvider

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai/"
DEFAULT_MODEL = "gemini-2.5-flash"

# Friendly preset keys for the common Gemini ids.
_PRESETS = {
    "gemini-flash": "gemini-2.5-flash",
    "gemini-pro": "gemini-2.5-pro",
    "gemini-flash-lite": "gemini-2.5-flash-lite",
}


class GeminiProvider(OpenAICompatibleProvider):
    name = "gemini"
    default_model = DEFAULT_MODEL
    base_url = GEMINI_BASE_URL
    base_url_env = "GEMINI_BASE_URL"
    api_key_envs = ("GEMINI_API_KEY", "GOOGLE_API_KEY")

    def _resolve_model(self, name: str) -> str:
        return _PRESETS.get(name, name)
