#!/usr/bin/env python3
"""Generate synthetic train/test datasets from the room simulator.

Stands in for real router captures so Phases 1-3 run and are measurable with no
hardware. Each sample places the obstacle at a random position (or leaves the
room empty), and records multi-node CSI + the ground-truth grid cell.

    python scripts/simulate_room.py --train 2500 --test 800
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from wifi_csi_spatial import load_config
from wifi_csi_spatial.capture.synthetic import RoomSimulatorSource
from wifi_csi_spatial.dataset import SpatialDataset
from wifi_csi_spatial.geometry.room import localization_cell


def _build(cfg, n: int, seed: int, p_empty: float) -> SpatialDataset:
    src = RoomSimulatorSource(cfg, moving=False, seed=seed)
    rng = np.random.default_rng(seed + 1)
    empty = cfg.n_cells
    csis, labels, xys = [], [], []
    for _ in range(n):
        if rng.random() < p_empty:
            obs, label, xy = None, empty, (np.nan, np.nan)
        else:
            obs = (rng.uniform(0.3, cfg.room_w - 0.3),
                   rng.uniform(0.3, cfg.room_h - 0.3))
            label, xy = localization_cell(obs, cfg), obs
        csis.append(src.sample(obs).csi)
        labels.append(label)
        xys.append(xy)
    return SpatialDataset(np.stack(csis), np.array(labels),
                          np.array(xys, dtype=float), cfg.n_cells)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--train", type=int, default=2500)
    ap.add_argument("--test", type=int, default=800)
    ap.add_argument("--p-empty", type=float, default=0.2)
    args = ap.parse_args()

    cfg = load_config()
    out = Path(cfg.data_dir)
    tr = _build(cfg, args.train, seed=1, p_empty=args.p_empty)
    te = _build(cfg, args.test, seed=999, p_empty=args.p_empty)
    tr.save(out / "train.npz")
    te.save(out / "test.npz")
    print(f"train: {len(tr)} samples  |  test: {len(te)} samples")
    print(f"room {cfg.room_w}x{cfg.room_h} m, {cfg.n_rx} nodes, "
          f"{cfg.n_cells} cells (+empty), {cfg.n_subcarriers} subcarriers")
    print(f"saved -> {out}/train.npz, {out}/test.npz")


if __name__ == "__main__":
    main()
