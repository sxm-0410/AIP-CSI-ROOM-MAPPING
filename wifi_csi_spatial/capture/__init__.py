"""Capture backends — multi-node, one interface.

Every backend yields the same :class:`Snapshot`: CSI for all TX->RX links at one
instant, shape ``(n_rx, n_subcarriers)``. Phase 2 fuses those links; nothing
downstream cares whether they came from a router, ESP32 nodes, or the simulator.
"""
from __future__ import annotations

from .base import Snapshot, MultiNodeSource, collect


def open_source(cfg, moving: bool = True) -> MultiNodeSource:
    """Factory: build the capture backend named by ``cfg.backend``."""
    backend = cfg.backend.lower()
    if backend == "synthetic":
        from .synthetic import RoomSimulatorSource
        return RoomSimulatorSource(cfg, moving=moving)
    if backend == "router":
        from .router import RouterSource
        return RouterSource(cfg)
    if backend == "esp32":
        from .esp32 import ESP32Source
        return ESP32Source(cfg)
    raise ValueError(f"unknown backend: {cfg.backend!r}")


__all__ = ["Snapshot", "MultiNodeSource", "collect", "open_source"]
