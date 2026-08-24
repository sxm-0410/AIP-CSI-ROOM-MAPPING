"""Labelled sample storage for Phases 1-2.

A dataset is a stack of snapshots with, for each, the obstacle's grid cell
(``EMPTY`` when the room is empty) and its true position. Stored as one compact
``.npz``.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class SpatialDataset:
    csi: np.ndarray       # (N, R, S) complex
    label: np.ndarray     # (N,) int   -> cell index, or EMPTY (= n_cells)
    xy: np.ndarray        # (N, 2) float, nan when empty
    n_cells: int          # so EMPTY == n_cells is unambiguous

    @property
    def empty_class(self) -> int:
        return self.n_cells

    def __len__(self) -> int:
        return int(self.csi.shape[0])

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(path, csi=self.csi, label=self.label,
                            xy=self.xy, n_cells=self.n_cells)
        return path

    @staticmethod
    def load(path: str | Path) -> "SpatialDataset":
        with np.load(path, allow_pickle=False) as z:
            return SpatialDataset(z["csi"], z["label"], z["xy"],
                                  int(z["n_cells"]))
