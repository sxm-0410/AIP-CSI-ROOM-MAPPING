"""Synthetic CSI sessions: lets the whole pipeline run and be tested with no hardware.

Each zone has a fixed multipath 'fingerprint'; a person adds that fingerprint
plus temporal fluctuation. Sessions differ by a slow gain drift, mimicking
day-to-day change (so session-held-out evaluation is meaningful).
"""
from __future__ import annotations

import numpy as np

S = 64


def make_session(zones, seconds=20.0, fs=50.0, seed=0, shift=0.6):
    """-> dict zone -> amplitudes (T, S). ``zones`` includes 'empty'."""
    base = np.random.default_rng(1234)                  # same room every session
    room = 20 + 8 * np.abs(base.normal(size=S))
    fp = {z: base.normal(size=S) * shift * 6 for z in zones if z != "empty"}
    rng = np.random.default_rng(seed)                   # per-session randomness
    gain = rng.uniform(0.9, 1.1)
    out = {}
    n = int(seconds * fs)
    for z in zones:
        amp = np.tile(room * gain, (n, 1))
        if z != "empty":
            amp = amp + fp[z] + rng.normal(0, 1.5, (n, S))     # person: shift + wobble
        amp = amp + rng.normal(0, 0.4, (n, S))
        amp[:, 0] = 0                                          # a dead guard tone
        out[z] = np.clip(amp, 0, None).astype(np.float32)
    return out
