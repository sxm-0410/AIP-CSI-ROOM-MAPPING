#!/usr/bin/env python3
"""Capture multi-node snapshots from the configured backend into a dataset.

    # router today (label the obstacle's grid cell for supervised Phase 1/2):
    python scripts/capture.py --cell 5 --frames 500

    # empty room (for Phase 3 boundary scan):
    python scripts/capture.py --empty --frames 500

Switching to ESP32 later only needs --backend esp32 (or config).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from wifi_csi_spatial import load_config
from wifi_csi_spatial.capture import open_source, collect
from wifi_csi_spatial.dataset import SpatialDataset
from wifi_csi_spatial.geometry.room import cell_center


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--cell", type=int, help="ground-truth grid cell of obstacle")
    g.add_argument("--empty", action="store_true", help="empty room")
    ap.add_argument("--frames", type=int, default=500)
    ap.add_argument("--backend", default=None)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    cfg = load_config()
    if args.backend:
        cfg.backend = args.backend

    with open_source(cfg, moving=False) as src:
        csi, _ = collect(src, args.frames)          # (N, R, S)

    if args.empty:
        label = np.full(len(csi), cfg.n_cells)
        xy = np.full((len(csi), 2), np.nan)
        tag = "empty"
    else:
        label = np.full(len(csi), args.cell)
        xy = np.tile(cell_center(args.cell, cfg), (len(csi), 1))
        tag = f"cell{args.cell}"

    out = Path(args.out or f"{cfg.data_dir}/capture_{tag}.npz")
    SpatialDataset(csi, label, xy, cfg.n_cells).save(out)
    print(f"captured {len(csi)} snapshots x {cfg.n_rx} nodes -> {out}")


if __name__ == "__main__":
    main()
