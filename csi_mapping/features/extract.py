"""Feature extraction  (roadmap step 2: "Collect & extract").

Slide a window over the cleaned amplitude/phase streams and summarise each
window into a fixed-length vector the classifier can eat. Features are the
usual CSI-sensing staples, kept compact and interpretable:

  * per-subcarrier mean & std amplitude   (where in the room energy lands)
  * per-subcarrier std of phase           (motion-induced phase jitter)
  * temporal amplitude variance           (how much the channel moves)
  * mean RSSI-like total power

This is intentionally a strong classical baseline; the CNN/BiLSTM path from the
roadmap can later consume the raw windows instead of these summaries.
"""
from __future__ import annotations

import numpy as np


def feature_names(n_sub: int) -> list[str]:
    names = [f"amp_mean_{i}" for i in range(n_sub)]
    names += [f"amp_std_{i}" for i in range(n_sub)]
    names += [f"phase_std_{i}" for i in range(n_sub)]
    names += ["amp_temporal_var", "total_power"]
    return names


def _window_vector(amp_win: np.ndarray, phase_win: np.ndarray) -> np.ndarray:
    amp_mean = amp_win.mean(axis=0)
    amp_std = amp_win.std(axis=0)
    phase_std = phase_win.std(axis=0)
    temporal_var = np.atleast_1d(amp_win.var(axis=0).mean())
    total_power = np.atleast_1d((amp_win ** 2).mean())
    return np.concatenate([amp_mean, amp_std, phase_std,
                           temporal_var, total_power])


def window_features(amp: np.ndarray, phase: np.ndarray,
                    window: int, hop: int) -> np.ndarray:
    """Turn ``(T, S)`` amplitude/phase into ``(n_windows, F)`` features."""
    T = amp.shape[0]
    if T < window:
        return np.empty((0, 3 * amp.shape[1] + 2))
    rows = [
        _window_vector(amp[s:s + window], phase[s:s + window])
        for s in range(0, T - window + 1, hop)
    ]
    return np.vstack(rows)
