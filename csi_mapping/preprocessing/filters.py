"""Amplitude denoising  (roadmap step 1: "Clean the signal").

Two stages, applied along time, independently per subcarrier:

  1. Hampel filter  -> rejects impulsive outliers (bad packets, bursts).
  2. Butterworth low-pass -> removes high-frequency measurement noise while
     keeping the slow variation caused by human movement.

Butterworth uses SciPy when available and falls back to a simple exponential
moving average so the pipeline still runs in a numpy-only environment.
"""
from __future__ import annotations

import numpy as np


def hampel(x: np.ndarray, window: int = 5, n_sigma: float = 3.0) -> np.ndarray:
    """Replace outliers with the local median (Hampel identifier).

    Works on ``(T,)`` or ``(T, S)`` arrays, filtering along axis 0.
    """
    x = np.asarray(x, dtype=float)
    single = x.ndim == 1
    a = x[:, None] if single else x
    T = a.shape[0]
    out = a.copy()
    k = 1.4826  # MAD -> std for Gaussian data
    for i in range(T):
        lo, hi = max(0, i - window), min(T, i + window + 1)
        seg = a[lo:hi]
        med = np.median(seg, axis=0)
        mad = k * np.median(np.abs(seg - med), axis=0)
        thresh = n_sigma * mad
        # deviation beyond threshold is an outlier; when MAD==0 (locally
        # constant window) any nonzero deviation is a lone spike -> flag it.
        bad = np.abs(a[i] - med) > thresh
        out[i] = np.where(bad, med, a[i])
    return out[:, 0] if single else out


def butterworth_lowpass(x: np.ndarray, cutoff_hz: float, fs: float,
                        order: int = 4) -> np.ndarray:
    """Zero-phase low-pass along axis 0. SciPy if present, else EMA fallback."""
    x = np.asarray(x, dtype=float)
    nyq = 0.5 * fs
    if cutoff_hz >= nyq:
        return x
    try:
        from scipy.signal import butter, filtfilt
        b, a = butter(order, cutoff_hz / nyq, btype="low")
        pad = 3 * max(len(a), len(b))
        if x.shape[0] <= pad:  # too short for filtfilt padding
            return x
        return filtfilt(b, a, x, axis=0)
    except ImportError:
        alpha = min(1.0, cutoff_hz / nyq)
        out = np.empty_like(x)
        out[0] = x[0]
        for i in range(1, x.shape[0]):
            out[i] = alpha * x[i] + (1 - alpha) * out[i - 1]
        return out


def clean_amplitude(amp: np.ndarray, cfg) -> np.ndarray:
    """Full amplitude cleaning: Hampel -> Butterworth. Shape ``(T, S)``."""
    a = hampel(amp, cfg.hampel_window, cfg.hampel_sigma)
    a = butterworth_lowpass(a, cfg.butter_cutoff_hz, cfg.sample_rate_hz,
                            cfg.butter_order)
    return a
