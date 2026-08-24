"""Phase sanitization  (CFO/SFO removal).

Raw CSI phase carries a near-linear tilt across subcarriers from carrier- and
sampling-frequency offset that changes every frame and swamps the geometry
information. The standard fix is a per-row linear detrend: unwrap phase across
subcarriers, fit a line (slope = SFO, intercept = CFO), subtract it.
"""
from __future__ import annotations

import numpy as np


def sanitize_phase(csi: np.ndarray) -> np.ndarray:
    """Remove the CFO/SFO linear phase term. Works on ``(S,)`` or ``(..., S)``.

    Amplitude is preserved; only the phase is de-tilted along the last axis.
    """
    x = np.asarray(csi)
    x2 = x.reshape(-1, x.shape[-1])
    S = x2.shape[1]
    k = np.arange(S)
    amp = np.abs(x2)
    phase = np.unwrap(np.angle(x2), axis=1)

    kbar = k.mean()
    denom = np.sum((k - kbar) ** 2)
    a = np.sum((k - kbar) * (phase - phase.mean(axis=1, keepdims=True)),
               axis=1) / denom
    b = phase.mean(axis=1) - a * kbar
    clean = phase - (a[:, None] * k[None, :] + b[:, None])

    out = (amp * np.exp(1j * clean)).astype(np.complex64)
    return out.reshape(x.shape)
