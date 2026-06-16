"""LLM providers and selection.

``SANDCASTLEGM_PROVIDER`` picks a backend explicitly (``openrouter`` |
``anthropic``); otherwise the default is auto-detected from whichever API key is
present, preferring OpenRouter.
"""

from __future__ import annotations

import os

from sandcastlegm.gm.providers.base import (
    LLMProvider,
    LLMResponse,
    LLMToolCall,
    ToolResult,
)
from sandcastlegm.gm.providers.anthropic_provider import AnthropicProvider
from sandcastlegm.gm.providers.openrouter import OpenRouterProvider

_FACTORIES = {
    "openrouter": OpenRouterProvider,
    "anthropic": AnthropicProvider,
}


def make_provider(name: str, model: str | None = None) -> LLMProvider:
    key = name.lower()
    if key not in _FACTORIES:
        raise KeyError(f"unknown provider {name!r}; have {sorted(_FACTORIES)}")
    return _FACTORIES[key](model=model)


def make_default_provider(model: str | None = None) -> LLMProvider | None:
    """Select a provider from env, or auto-detect from available API keys."""
    name = os.environ.get("SANDCASTLEGM_PROVIDER")
    if name and name.lower() in _FACTORIES:
        return make_provider(name, model)

    if os.environ.get("OPENROUTER_API_KEY"):
        return OpenRouterProvider(model=model)
    if os.environ.get("ANTHROPIC_API_KEY"):
        return AnthropicProvider(model=model)
    return None


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "LLMToolCall",
    "ToolResult",
    "OpenRouterProvider",
    "AnthropicProvider",
    "make_provider",
    "make_default_provider",
]
