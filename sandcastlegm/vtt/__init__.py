"""Virtual-tabletop adapters: export game state into open VTT formats."""

from sandcastlegm.vtt.base import VTTAdapter
from sandcastlegm.vtt.cocofolia import CocofoliaAdapter
from sandcastlegm.vtt.udonarium import UdonariumAdapter

ADAPTERS: dict[str, type[VTTAdapter]] = {
    CocofoliaAdapter.id: CocofoliaAdapter,
    UdonariumAdapter.id: UdonariumAdapter,
}


def get_adapter(adapter_id: str) -> VTTAdapter:
    if adapter_id not in ADAPTERS:
        raise KeyError(f"unknown VTT adapter {adapter_id!r}; have {sorted(ADAPTERS)}")
    return ADAPTERS[adapter_id]()


__all__ = ["VTTAdapter", "CocofoliaAdapter", "UdonariumAdapter", "ADAPTERS", "get_adapter"]
