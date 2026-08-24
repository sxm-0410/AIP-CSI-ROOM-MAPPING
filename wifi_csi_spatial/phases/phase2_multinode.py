"""Phase 2 — Multi-node sensing.

Fuse **all** TX->RX links. More independent viewpoints of the same obstacle
resolve the location ambiguities a single link suffers from, so localization
error drops. ``error_vs_nodes`` quantifies exactly that — the headline Phase 2
result.
"""
from __future__ import annotations

from ..config import Config
from ..dataset import SpatialDataset
from .common import Localizer


class Phase2Localizer(Localizer):
    def __init__(self, cfg: Config, links: list[int] | None = None):
        super().__init__(cfg, links=links or list(range(cfg.n_rx)))


def error_vs_nodes(train: SpatialDataset, test: SpatialDataset,
                   cfg: Config) -> dict[int, float]:
    """Localization error (metres) as the number of fused nodes grows."""
    out: dict[int, float] = {}
    for n in range(1, cfg.n_rx + 1):
        loc = Localizer(cfg, links=list(range(n))).fit(train)
        out[n] = loc.evaluate(test).loc_error_m
    return out
