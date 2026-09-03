"""Safe identifiers for future source-controlled mapping implementations.

This module deliberately contains no observation-transformation pipeline.
Database rows store these identifiers as metadata, never executable code.
"""

from __future__ import annotations


IMPLEMENTATION_KEYS = frozenset(
    {
        "IDENTITY",
        "NORMALIZE_AREA",
        "MAP_TRADE_FLOW",
        "MAP_PRODUCT_SCHEME",
        "MAP_PRODUCT",
        "MAP_UNIT",
    }
)


def is_supported_implementation_key(value: str) -> bool:
    return value in IMPLEMENTATION_KEYS
