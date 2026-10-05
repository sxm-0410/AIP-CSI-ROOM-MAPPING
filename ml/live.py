"""Streaming zone inference with probability smoothing."""
from __future__ import annotations

from collections import deque

import numpy as np

from . import preprocess as pp


class ZonePredictor:
    def __init__(self, bundle: dict, smooth: int = 5):
        self.m = bundle["model"]
        self.mask = bundle["mask"]
        self.classes = bundle["classes"]
        self.win, self.hop = bundle["win"], bundle["hop"]
        self._buf: deque = deque(maxlen=self.win)
        self._probs: deque = deque(maxlen=smooth)
        self._n = 0

    def push(self, amp: np.ndarray):
        """Feed one frame. Returns a result dict every ``hop`` frames, else None."""
        if amp.shape[0] != self.mask.shape[0]:
            return None                       # wrong subcarrier count: skip frame
        self._buf.append(amp)
        self._n += 1
        if len(self._buf) < self.win or self._n % self.hop:
            return None
        feats = pp.make_windows(np.stack(self._buf), self.mask,
                                self.win, self.hop)[-1:]
        self._probs.append(self.m.predict_proba(feats)[0])
        p = np.mean(self._probs, axis=0)
        return {"zone": self.classes[int(p.argmax())],
                "probs": dict(zip(self.classes, p.round(3).tolist()))}
