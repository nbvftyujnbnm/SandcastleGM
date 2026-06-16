"""Ruleset discovery and instantiation.

Built-in rulesets register themselves on import. Third-party "patches" can ship
as separate packages and advertise a ``sandcastlegm.rulesets`` entry point that
points at a :class:`~sandcastlegm.rulesets.base.Ruleset` subclass; calling
:func:`discover_plugins` loads them so they appear alongside the built-ins.
"""

from __future__ import annotations

import random
from typing import Type

from sandcastlegm.rulesets.base import Ruleset

_REGISTRY: dict[str, Type[Ruleset]] = {}


def register(ruleset_cls: Type[Ruleset]) -> Type[Ruleset]:
    """Register a ruleset class. Usable as a decorator."""
    rid = ruleset_cls.id
    if not rid or rid == "base":
        raise ValueError(f"{ruleset_cls.__name__} must define a unique 'id'")
    _REGISTRY[rid] = ruleset_cls
    return ruleset_cls


def available() -> dict[str, str]:
    """Map of ``ruleset_id -> display name`` for every registered system."""
    return {rid: cls.name for rid, cls in sorted(_REGISTRY.items())}


def get(ruleset_id: str) -> Type[Ruleset]:
    if ruleset_id not in _REGISTRY:
        raise KeyError(
            f"unknown ruleset {ruleset_id!r}; available: {sorted(_REGISTRY)}"
        )
    return _REGISTRY[ruleset_id]


def create(ruleset_id: str, rng: random.Random | None = None) -> Ruleset:
    """Instantiate a registered ruleset by id."""
    return get(ruleset_id)(rng=rng)


def discover_plugins() -> list[str]:
    """Load external ruleset patches advertised via entry points.

    Returns the ids newly discovered. Safe to call repeatedly.
    """
    found: list[str] = []
    try:
        from importlib.metadata import entry_points
    except ImportError:  # pragma: no cover - very old Python
        return found

    eps = entry_points()
    selected = (
        eps.select(group="sandcastlegm.rulesets")
        if hasattr(eps, "select")
        else eps.get("sandcastlegm.rulesets", [])  # type: ignore[attr-defined]
    )
    for ep in selected:
        try:
            cls = ep.load()
            register(cls)
            found.append(cls.id)
        except Exception:  # noqa: BLE001 - a bad patch must not break startup
            continue
    return found
