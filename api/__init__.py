"""API integration layer for setu plugin."""

from __future__ import annotations

from .providers import (
    AtriProvider,
    CustomApiProvider,
    LoliconProvider,
    MultiApiProvider,
    SetuImageProvider,
    SexNyanRunProvider,
    get_provider,
)

__all__ = [
    "SetuImageProvider",
    "MultiApiProvider",
    "LoliconProvider",
    "AtriProvider",
    "SexNyanRunProvider",
    "CustomApiProvider",
    "get_provider",
]
