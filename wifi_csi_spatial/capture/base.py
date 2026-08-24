"""The one interface every capture backend implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from itertools import islice
from typing import Iterator

import numpy as np


@dataclass
class Snapshot:
    """CSI for every TX->RX link at one instant.

    Attributes
    ----------
    timestamp : float
    csi : np.ndarray
        Complex, shape ``(n_rx, n_subcarriers)`` — one row per link.
    obstacle : tuple[float, float] | None
        Ground-truth obstacle position (synthetic only; ``None`` otherwise).
    """
    timestamp: float
    csi: np.ndarray
    obstacle: tuple[float, float] | None = None

    @property
    def n_rx(self) -> int:
        return int(self.csi.shape[0])

    @property
    def n_subcarriers(self) -> int:
        return int(self.csi.shape[1])


class MultiNodeSource(ABC):
    """Streams :class:`Snapshot` objects. Usable as a context manager."""

    @abstractmethod
    def snapshots(self) -> Iterator[Snapshot]:
        ...

    def read(self, n: int) -> list[Snapshot]:
        return list(islice(self.snapshots(), n))

    def close(self) -> None:
        pass

    def __enter__(self) -> "MultiNodeSource":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def collect(source: MultiNodeSource, n: int):
    """Drain ``n`` snapshots into ``(csi (n, R, S), obstacles (n, 2))``."""
    snaps = source.read(n)
    if not snaps:
        raise RuntimeError("capture source produced no snapshots")
    csi = np.stack([s.csi for s in snaps]).astype(np.complex64)
    obs = np.array([s.obstacle if s.obstacle is not None else (np.nan, np.nan)
                    for s in snaps], dtype=float)
    return csi, obs
