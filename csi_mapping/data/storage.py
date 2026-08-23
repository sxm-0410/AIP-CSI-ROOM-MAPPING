"""Session storage.

A *session* is one continuous capture of one zone. We store each as a compact
``.npz`` (numpy only — no parquet/pandas needed to read the raw data), which
keeps the "collect across zones, over multiple sessions" workflow from the
roadmap dependency-light and git-friendly.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class Session:
    session_id: str
    zone: str                 # ground-truth label
    timestamps: np.ndarray    # (T,)
    csi: np.ndarray           # (T, S) complex

    @property
    def n_frames(self) -> int:
        return int(self.csi.shape[0])

    @property
    def n_subcarriers(self) -> int:
        return int(self.csi.shape[1])


def save_session(session: Session, data_dir: str | Path) -> Path:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{session.session_id}.npz"
    np.savez_compressed(
        path,
        session_id=session.session_id,
        zone=session.zone,
        timestamps=session.timestamps,
        csi=session.csi,
    )
    return path


def load_session(path: str | Path) -> Session:
    with np.load(path, allow_pickle=False) as z:
        return Session(
            session_id=str(z["session_id"]),
            zone=str(z["zone"]),
            timestamps=z["timestamps"],
            csi=z["csi"],
        )


def load_dataset(data_dir: str | Path) -> list[Session]:
    """Load every session in a directory, sorted by id (stable CV folds)."""
    data_dir = Path(data_dir)
    return [load_session(p) for p in sorted(data_dir.glob("*.npz"))]
