"""Capture backends.

Every backend yields the same :class:`CSIFrame`, so the rest of the pipeline
never knows (or cares) whether the signal came from a router, an ESP32, or a
synthetic generator. Pick one with :func:`open_source`.
"""
from __future__ import annotations

from .base import CSIFrame, CSISource, collect_session


def open_source(cfg, zone: str | None = None) -> CSISource:
    """Factory: build the capture backend named by ``cfg.backend``."""
    backend = cfg.backend.lower()
    if backend == "synthetic":
        from .synthetic import SyntheticSource
        return SyntheticSource(cfg, zone=zone)
    if backend == "router":
        from .router import RouterSource
        return RouterSource(cfg)
    if backend == "esp32":
        from .esp32 import ESP32Source
        return ESP32Source(cfg)
    raise ValueError(f"unknown backend: {cfg.backend!r}")


__all__ = ["CSIFrame", "CSISource", "collect_session", "open_source"]
