"""Session files: CSV with columns  zone,ms,rssi,a0..a{S-1}  (one per recording session)."""
from __future__ import annotations

import csv
from pathlib import Path

import numpy as np


def save_session(path, rows):
    """``rows``: iterable of (zone, ms, rssi, amp[S])."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as fh:
        w = csv.writer(fh)
        for zone, ms, rssi, amp in rows:
            w.writerow([zone, ms, rssi, *[f"{a:.2f}" for a in amp]])


def load_session(path):
    """-> dict zone -> amplitudes (T, S), in recorded order."""
    by: dict[str, list] = {}
    with Path(path).open() as fh:
        for r in csv.reader(fh):
            if len(r) < 4:
                continue
            by.setdefault(r[0], []).append([float(v) for v in r[3:]])
    out = {}
    for z, rows in by.items():
        n = min(len(r) for r in rows)                  # guard against ragged rows
        out[z] = np.array([r[:n] for r in rows], dtype=np.float32)
    return out
