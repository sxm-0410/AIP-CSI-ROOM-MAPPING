"""The glue: capture/session -> cleaned features.

One function, used by both training (offline, over saved sessions) and the live
demo (online, over the last N frames). Keeping the exact same transform on both
sides is what stops train/serve skew.
"""
from __future__ import annotations

import numpy as np

from .config import Config
from .data.storage import Session
from .preprocessing import sanitize_phase, clean_amplitude
from .features import window_features


def frames_to_features(csi: np.ndarray, cfg: Config) -> np.ndarray:
    """``(T, S)`` complex CSI -> ``(n_windows, F)`` feature matrix."""
    clean = sanitize_phase(csi)
    amp = clean_amplitude(np.abs(clean), cfg)
    phase = np.angle(clean)
    return window_features(amp, phase, cfg.window, cfg.hop)


def session_to_features(session: Session, cfg: Config):
    """Return ``(X, y)`` where every window inherits the session's zone."""
    X = frames_to_features(session.csi, cfg)
    y = np.array([session.zone] * len(X))
    return X, y


def build_dataset(sessions: list[Session], cfg: Config):
    """Stack all sessions into ``(X, y, groups)`` for grouped CV."""
    Xs, ys, groups = [], [], []
    for s in sessions:
        X, y = session_to_features(s, cfg)
        if len(X):
            Xs.append(X)
            ys.append(y)
            groups.append(np.array([s.session_id] * len(X)))
    if not Xs:
        raise RuntimeError("no windows extracted — sessions too short?")
    return np.vstack(Xs), np.concatenate(ys), np.concatenate(groups)
