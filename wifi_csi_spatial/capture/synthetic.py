"""Synthetic room-simulator source.

Turns the :class:`Room` geometry into live CSI so the whole pipeline — and
Phases 1-3 — run and are testable without hardware. On top of the physical
multipath we add the real-world nuisances the cleaning stage removes:

  * per-frame CFO/SFO linear phase ramp   (killed by phase sanitization)
  * sparse impulse outliers               (killed by the Hampel filter)
  * broadband noise                       (smoothed by Butterworth)

``moving=True`` random-walks a single obstacle around the room (for the live
demo); ``moving=False`` with ``obstacle=None`` yields the empty room used for
Phase 3 boundary estimation.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np

from .base import Snapshot, MultiNodeSource
from ..geometry.room import Room, subcarrier_freqs, synth_csi


class RoomSimulatorSource(MultiNodeSource):
    def __init__(self, cfg, obstacle: tuple[float, float] | None = "random",
                 moving: bool = True, seed: int | None = None):
        self.cfg = cfg
        self.room = Room.from_config(cfg)
        self.freqs = subcarrier_freqs(cfg.n_subcarriers)
        self.fs = cfg.sample_rate_hz
        self.moving = moving
        self.rng = np.random.default_rng(seed)
        if obstacle == "random":
            self._pos = self._rand_pos()
        else:
            self._pos = np.array(obstacle) if obstacle is not None else None

    def _rand_pos(self) -> np.ndarray:
        return np.array([self.rng.uniform(0.3, self.cfg.room_w - 0.3),
                         self.rng.uniform(0.3, self.cfg.room_h - 0.3)])

    def _step(self) -> None:
        if self._pos is None or not self.moving:
            return
        self._pos = self._pos + self.rng.normal(0, 0.08, 2)
        self._pos[0] = np.clip(self._pos[0], 0.3, self.cfg.room_w - 0.3)
        self._pos[1] = np.clip(self._pos[1], 0.3, self.cfg.room_h - 0.3)

    def _frame(self, t: float) -> Snapshot:
        obs = None if self._pos is None else tuple(self._pos)
        rows = []
        for rx in self.room.rx:
            csi = synth_csi(self.room.link_paths(rx, obs), self.freqs)
            k = np.arange(self.cfg.n_subcarriers)
            cfo = self.rng.uniform(-0.02, 0.02)
            csi = csi * np.exp(2j * np.pi * cfo * k)          # CFO/SFO ramp
            noise = (self.rng.normal(0, 0.01, csi.shape)
                     + 1j * self.rng.normal(0, 0.01, csi.shape))
            csi = csi + noise
            if self.rng.random() < 0.02:                       # impulse outlier
                bad = self.rng.integers(0, self.cfg.n_subcarriers)
                csi[bad] *= self.rng.uniform(5, 10)
            rows.append(csi)
        return Snapshot(t, np.stack(rows).astype(np.complex64), obs)

    def sample(self, obstacle: tuple[float, float] | None) -> Snapshot:
        """One snapshot for a given obstacle position (or empty room)."""
        self._pos = None if obstacle is None else np.array(obstacle, float)
        return self._frame(0.0)

    def snapshots(self) -> Iterator[Snapshot]:
        t, dt = 0.0, 1.0 / self.fs
        while True:
            yield self._frame(t)
            self._step()
            t += dt


def empty_room_reference(cfg, n_avg: int = 64, noise: float = 0.003,
                         seed: int = 0) -> np.ndarray:
    """CFO-calibrated, noise-averaged empty-room CSI ``(R, S)`` for Phase 3.

    Models a one-time boundary-mapping scan: no obstacle, CFO calibrated out,
    many frames averaged to suppress noise so the wall reflections stand clean.
    """
    room = Room.from_config(cfg)
    freqs = subcarrier_freqs(cfg.n_subcarriers)
    rng = np.random.default_rng(seed)
    acc = np.zeros((cfg.n_rx, cfg.n_subcarriers), dtype=complex)
    for _ in range(n_avg):
        for i, rx in enumerate(room.rx):
            csi = synth_csi(room.link_paths(rx, None), freqs)
            acc[i] += csi + (rng.normal(0, noise, csi.shape)
                             + 1j * rng.normal(0, noise, csi.shape))
    return (acc / n_avg).astype(np.complex64)
