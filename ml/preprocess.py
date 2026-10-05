"""Amplitude cleaning and windowed features."""
from __future__ import annotations

import numpy as np
from scipy.ndimage import median_filter

WIN = 50      # frames per window (1 s at 50 Hz)
HOP = 10


def hampel_time(x: np.ndarray, size: int = 5, n_sigma: float = 3.0) -> np.ndarray:
    """Replace per-subcarrier spikes along time (axis 0) with the local median."""
    med = median_filter(x, size=(size, 1), mode="nearest")
    dev = np.abs(x - med)
    mad = 1.4826 * median_filter(dev, size=(size, 1), mode="nearest")
    return np.where(dev > n_sigma * mad + 1e-6, med, x)


def active_mask(amps: np.ndarray) -> np.ndarray:
    """Subcarriers that carry signal (guard/DC tones are always ~0)."""
    return amps.mean(axis=0) > 1e-3


def window_features(w: np.ndarray) -> np.ndarray:
    """``w`` (T, S) amplitudes -> [per-subcarrier mean, per-subcarrier std, motion energy].

    Each frame is divided by its own mean first, which cancels receiver gain (AGC)
    jumps and leaves the multipath *shape* that encodes position.
    """
    w = w / (w.mean(axis=1, keepdims=True) + 1e-6)
    mean, std = w.mean(axis=0), w.std(axis=0)
    return np.concatenate([mean, std, [std.mean()]]).astype(np.float32)


def make_windows(amps: np.ndarray, mask: np.ndarray, win: int = WIN, hop: int = HOP):
    """Clean ``amps`` (T, S) and return features ``(N, F)`` for sliding windows."""
    x = hampel_time(amps[:, mask])
    if len(x) < win:
        return np.empty((0, 2 * x.shape[1] + 1), np.float32)
    return np.stack([window_features(x[i:i + win])
                     for i in range(0, len(x) - win + 1, hop)])
