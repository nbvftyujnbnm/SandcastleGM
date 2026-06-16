"""SandcastleGM — an AI Game Master for tabletop RPGs.

Public surface:
    - ``core``: ruleset-agnostic domain (dice, state, events)
    - ``rulesets``: the pluggable "patch" layer; ships with Sandcastle
    - ``gm``: the AI Game Master engine (optional ``anthropic`` dependency)
    - ``vtt``: virtual-tabletop adapters (Udonarium, Cocofolia)
    - ``server``: multiplayer session server (optional ``fastapi`` dependency)
"""

__version__ = "0.1.0"
