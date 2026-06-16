"""The AI Game Master: engine, tool surface, prompts, and LLM providers.

The model backends (OpenRouter via the ``openai`` SDK, Anthropic via
``anthropic``) are optional dependencies, imported lazily. The engine degrades
to a deterministic referee when no provider/key is available, so importing this
package never hard-fails.
"""

from sandcastlegm.gm.engine import AIGameMaster, GMTurn
from sandcastlegm.gm.providers import (
    LLMProvider,
    LLMResponse,
    LLMToolCall,
    ToolResult,
    make_default_provider,
    make_provider,
)
from sandcastlegm.gm.tools import GMContext, TOOL_SPECS, execute_tool, tool_names

__all__ = [
    "AIGameMaster",
    "GMTurn",
    "GMContext",
    "TOOL_SPECS",
    "execute_tool",
    "tool_names",
    "LLMProvider",
    "LLMResponse",
    "LLMToolCall",
    "ToolResult",
    "make_provider",
    "make_default_provider",
]
