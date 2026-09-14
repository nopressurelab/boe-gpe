"""Source adapters. The name used in sources.json is resolved here."""

from __future__ import annotations

from .base import Adapter, RawItem
from .boe_sumario import BoeSumarioAdapter
from .opendatasoft import OpenDataSoftAdapter
from .rss import RssAdapter

REGISTRY: dict[str, type[Adapter]] = {
    "boe_sumario": BoeSumarioAdapter,
    "rss": RssAdapter,
    "opendatasoft": OpenDataSoftAdapter,
}


def get(name: str) -> type[Adapter]:
    try:
        return REGISTRY[name]
    except KeyError:
        raise KeyError(
            f"Unknown adapter '{name}'. Available: {', '.join(sorted(REGISTRY))}"
        ) from None


__all__ = ["Adapter", "RawItem", "REGISTRY", "get"]
