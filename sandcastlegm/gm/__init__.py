"""The AI Game Master: engine, tool surface, and prompt assembly.

The ``anthropic`` SDK is an optional dependency (extra ``gm``). The engine
imports it lazily and degrades to a deterministic referee when it (or an API
key) is missing, so importing this package never hard-fails.
"""

from sandcastlegm.gm.engine import AIGameMaster, GMTurn
from sandcastlegm.gm.tools import GMContext, TOOL_SPECS, execute_tool, tool_names

__all__ = [
    "AIGameMaster",
    "GMTurn",
    "GMContext",
    "TOOL_SPECS",
    "execute_tool",
    "tool_names",
]
