"""Turn cleaned CSI into model-ready feature vectors.

Per link we keep the sanitized amplitude and phase across subcarriers; a sample
concatenates the chosen links end to end. ``links`` is what makes Phase 1
(one link) and Phase 2 (all links) the *same* code with a different fan-in.
The concatenated vector then goes through PCA -> 1D-CNN downstream.
"""
from __future__ import annotations

import numpy as np

from ..preprocessing import sanitize_phase, clean_amplitude


def clean_link(csi_row: np.ndarray, cfg):
    """Clean one link's CSI ``(S,)`` -> ``(amp (S,), phase (S,))``."""
    clean = sanitize_phase(csi_row)
    amp = clean_amplitude(np.abs(clean), cfg)
    phase = np.angle(clean)
    return amp, phase


def snapshot_features(csi_rs: np.ndarray, cfg,
                      links: list[int] | None = None) -> np.ndarray:
    """One snapshot ``(R, S)`` -> 1-D feature vector over the chosen links."""
    if links is None:
        links = list(range(csi_rs.shape[0]))
    parts = []
    for i in links:
        amp, phase = clean_link(csi_rs[i], cfg)
        parts.append(amp)
        parts.append(phase)
    return np.concatenate(parts).astype(np.float32)


def batch_features(csi_nrs: np.ndarray, cfg,
                   links: list[int] | None = None) -> np.ndarray:
    """Stack of snapshots ``(N, R, S)`` -> feature matrix ``(N, F)``."""
    return np.stack([snapshot_features(c, cfg, links) for c in csi_nrs])
