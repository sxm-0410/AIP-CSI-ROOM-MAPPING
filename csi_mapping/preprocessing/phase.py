"""Phase sanitization  (roadmap step 1: "Clean the signal").

Raw CSI phase is unusable straight off the radio: carrier-frequency offset
(CFO) and sampling-frequency offset (SFO) add a near-linear tilt across
subcarriers that changes every frame and swamps the tiny, motion-induced phase
shifts we actually care about.

The standard fix (Nexmon / Atheros CSI literature) is a per-frame linear
detrend: unwrap the phase across subcarriers, fit a line (slope = SFO,
intercept = CFO), and subtract it. What survives is the calibrated phase.
"""
from __future__ import annotations

import numpy as np


def sanitize_phase(csi: np.ndarray) -> np.ndarray:
    """Remove the CFO/SFO linear phase term from each CSI frame.

    Parameters
    ----------
    csi : np.ndarray
        Complex CSI, shape ``(T, S)`` (or ``(S,)`` for a single frame).

    Returns
    -------
    np.ndarray
        Complex CSI with amplitude preserved and phase de-tilted.
    """
    single = csi.ndim == 1
    x = np.atleast_2d(csi)
    S = x.shape[1]
    k = np.arange(S)
    amp = np.abs(x)
    phase = np.unwrap(np.angle(x), axis=1)

    # least-squares line (slope a, intercept b) per frame, subtracted off
    kbar = k.mean()
    denom = np.sum((k - kbar) ** 2)
    a = np.sum((k - kbar) * (phase - phase.mean(axis=1, keepdims=True)),
               axis=1) / denom
    b = phase.mean(axis=1) - a * kbar
    clean_phase = phase - (a[:, None] * k[None, :] + b[:, None])

    out = amp * np.exp(1j * clean_phase)
    return out[0] if single else out
