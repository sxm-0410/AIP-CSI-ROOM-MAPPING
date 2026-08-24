"""Noise filtering  (deck: "Noise Filtering — Butterworth").

For per-snapshot inference these run **across the subcarrier axis** — a standard
way to denoise a channel-frequency-response:

  1. Hampel      -> rejects outlier subcarriers (bad/pilot tones, spikes).
  2. Butterworth -> low-passes the frequency response, removing high-frequency
     ripple while keeping the smooth multipath shape that encodes geometry.

Butterworth uses SciPy when present, else an EMA fallback, so the core still
runs numpy-only.
"""
from __future__ import annotations

import numpy as np


def hampel(x: np.ndarray, window: int = 5, n_sigma: float = 3.0,
           axis: int = -1) -> np.ndarray:
    """Replace outliers with the local median along ``axis``."""
    x = np.asarray(x, dtype=float)
    xm = np.moveaxis(x, axis, -1)
    n = xm.shape[-1]
    out = xm.copy()
    k = 1.4826
    for i in range(n):
        lo, hi = max(0, i - window), min(n, i + window + 1)
        seg = xm[..., lo:hi]
        med = np.median(seg, axis=-1)
        mad = k * np.median(np.abs(seg - med[..., None]), axis=-1)
        bad = np.abs(xm[..., i] - med) > n_sigma * mad
        out[..., i] = np.where(bad, med, xm[..., i])
    return np.moveaxis(out, -1, axis)


def butterworth_lowpass(x: np.ndarray, norm_cutoff: float, order: int = 4,
                        axis: int = -1) -> np.ndarray:
    """Zero-phase low-pass along ``axis``. ``norm_cutoff`` in (0, 1) of Nyquist."""
    x = np.asarray(x, dtype=float)
    norm_cutoff = float(np.clip(norm_cutoff, 1e-3, 0.99))
    try:
        from scipy.signal import butter, filtfilt
        b, a = butter(order, norm_cutoff, btype="low")
        if x.shape[axis] <= 3 * max(len(a), len(b)):
            return x
        return filtfilt(b, a, x, axis=axis)
    except ImportError:
        xm = np.moveaxis(x, axis, 0)
        out = np.empty_like(xm)
        out[0] = xm[0]
        for i in range(1, xm.shape[0]):
            out[i] = norm_cutoff * xm[i] + (1 - norm_cutoff) * out[i - 1]
        return np.moveaxis(out, 0, axis)


def clean_amplitude(amp: np.ndarray, cfg, axis: int = -1) -> np.ndarray:
    """Hampel -> Butterworth across subcarriers. ``amp`` shape ``(..., S)``."""
    a = hampel(amp, cfg.hampel_window, cfg.hampel_sigma, axis=axis)
    norm = min(0.9, cfg.butter_cutoff_hz / (0.5 * cfg.sample_rate_hz))
    return butterworth_lowpass(a, norm, cfg.butter_order, axis=axis)
