"""Rulesets: the pluggable "patch" layer.

Importing this package registers the built-in rulesets and pulls in any
third-party patches advertised through entry points, so that
:func:`~sandcastlegm.rulesets.registry.available` lists everything installed.
"""

from sandcastlegm.rulesets.base import (
    AbilityDef,
    CheckRequest,
    CheckResult,
    Ruleset,
)
from sandcastlegm.rulesets import registry

# Register built-ins by importing them.
from sandcastlegm.rulesets import sandcastle  # noqa: F401

# Load external patches if any are installed.
registry.discover_plugins()

__all__ = [
    "AbilityDef",
    "CheckRequest",
    "CheckResult",
    "Ruleset",
    "registry",
]
