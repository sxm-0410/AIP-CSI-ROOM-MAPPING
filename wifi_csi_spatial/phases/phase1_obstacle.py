"""Phase 1 — Single obstacle detection.

Using a **single** TX->RX link, decide whether an obstacle is present and, if
so, which coarse grid cell it occupies. This is the localizer restricted to one
link; Phase 2 shows what extra nodes buy you.
"""
from __future__ import annotations

from ..config import Config
from .common import Localizer


class Phase1Detector(Localizer):
    def __init__(self, cfg: Config, link: int = 0):
        super().__init__(cfg, links=[link])
