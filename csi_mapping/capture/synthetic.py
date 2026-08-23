"""Synthetic CSI generator.

Lets the whole pipeline run — and be tested — without any hardware. Each zone
gets a distinct, fixed multipath signature; on top we layer the real-world
nuisances the cleaning stage is meant to remove:

  * a per-frame CFO/SFO linear phase ramp  (killed by phase sanitization)
  * sparse impulate outliers               (killed by the Hampel filter)
  * broadband noise                        (smoothed by Butterworth)

So a model trained on synthetic data is genuinely learning the zone signature,
not the artifacts — the same thing we expect from router/ESP32 captures.
"""
from __future__ import annotations

import hashlib
from typing import Iterator

import numpy as np

from .base import CSIFrame, CSISource


def stable_seed(text: str) -> int:
    """Process-independent seed from a string.

    Python's builtin ``hash()`` is salted per process (PYTHONHASHSEED), which
    would give a zone a *different* fingerprint every run — so data generated in
    one process wouldn't match a model trained in another. hashlib is stable.
    """
    return int.from_bytes(hashlib.md5(text.encode()).digest()[:4], "little")


def _zone_signature(zone: str, n_sub: int) -> np.ndarray:
    """Deterministic complex multipath fingerprint for a zone."""
    rng = np.random.default_rng(stable_seed(zone))
    k = np.arange(n_sub)
    # a few multipath taps -> smooth frequency-selective fading
    sig = np.zeros(n_sub, dtype=complex)
    for _ in range(4):
        delay = rng.uniform(0, 6)
        gain = rng.uniform(0.4, 1.0) * np.exp(1j * rng.uniform(0, 2 * np.pi))
        sig += gain * np.exp(-2j * np.pi * delay * k / n_sub)
    return sig / np.max(np.abs(sig))


class SyntheticSource(CSISource):
    def __init__(self, cfg, zone: str | None = None, seed: int | None = None):
        self.cfg = cfg
        self.zone = zone or cfg.zone_names[0]
        self.n_sub = cfg.n_subcarriers
        self.fs = cfg.sample_rate_hz
        self.rng = np.random.default_rng(seed)
        self._sig = _zone_signature(self.zone, self.n_sub)
        # a per-session gain/phase offset so sessions are not identical
        self._session_gain = self.rng.uniform(0.8, 1.2)
        self._session_phase = self.rng.uniform(0, 2 * np.pi)

    def frames(self) -> Iterator[CSIFrame]:
        k = np.arange(self.n_sub)
        t = 0.0
        dt = 1.0 / self.fs
        base = self._sig * self._session_gain * np.exp(1j * self._session_phase)
        while True:
            # slow human-motion amplitude modulation of a couple of taps
            motion = 1.0 + 0.15 * np.sin(2 * np.pi * 0.5 * t + k / self.n_sub)
            cfo = self.rng.uniform(-0.05, 0.05)            # residual CFO
            ramp = np.exp(2j * np.pi * cfo * k)            # linear phase tilt
            noise = (self.rng.normal(0, 0.03, self.n_sub)
                     + 1j * self.rng.normal(0, 0.03, self.n_sub))
            csi = base * motion * ramp + noise
            # sparse impulse outliers (~1% of samples)
            if self.rng.random() < 0.01:
                bad = self.rng.integers(0, self.n_sub)
                csi[bad] *= self.rng.uniform(5, 12)
            yield CSIFrame(timestamp=t, csi=csi.astype(np.complex64),
                           rssi=-45.0 + self.rng.normal(0, 1.5))
            t += dt
