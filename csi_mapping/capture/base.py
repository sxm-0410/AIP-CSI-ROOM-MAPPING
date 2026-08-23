"""The one interface every capture backend implements."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from itertools import islice
from typing import Iterator

import numpy as np


@dataclass
class CSIFrame:
    """A single CSI measurement.

    Attributes
    ----------
    timestamp : float
        Seconds (monotonic or epoch).
    csi : np.ndarray
        Complex array, shape ``(n_subcarriers,)``. Amplitude and phase are
        ``np.abs`` / ``np.angle`` of this.
    rssi : float
        Received signal strength (dBm), ``nan`` if unavailable.
    """
    timestamp: float
    csi: np.ndarray
    rssi: float = float("nan")

    @property
    def n_subcarriers(self) -> int:
        return int(self.csi.shape[-1])


class CSISource(ABC):
    """Streams :class:`CSIFrame` objects. Usable as a context manager."""

    @abstractmethod
    def frames(self) -> Iterator[CSIFrame]:
        """Yield frames until the source is exhausted (or forever, live)."""

    def read(self, n: int) -> list[CSIFrame]:
        """Grab the next ``n`` frames."""
        return list(islice(self.frames(), n))

    def close(self) -> None:  # backends with real handles override this
        pass

    def __enter__(self) -> "CSISource":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def collect_session(source: CSISource, n_frames: int):
    """Drain ``n_frames`` from a source into stacked arrays.

    Returns
    -------
    timestamps : np.ndarray, shape (T,)
    csi : np.ndarray, complex, shape (T, S)
    """
    frames = source.read(n_frames)
    if not frames:
        raise RuntimeError("capture source produced no frames")
    ts = np.array([f.timestamp for f in frames], dtype=float)
    csi = np.stack([f.csi for f in frames]).astype(np.complex64)
    return ts, csi
