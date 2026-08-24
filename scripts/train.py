#!/usr/bin/env python3
"""Train and evaluate Phases 1-3, then save models + a boundary preview.

    python scripts/train.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from wifi_csi_spatial import load_config
from wifi_csi_spatial.dataset import SpatialDataset
from wifi_csi_spatial.capture.synthetic import empty_room_reference
from wifi_csi_spatial.phases import (
    Phase1Detector, Phase2Localizer, error_vs_nodes, evaluate_boundary,
)


def main() -> None:
    cfg = load_config()
    data = Path(cfg.data_dir)
    if not (data / "train.npz").exists():
        raise SystemExit("no dataset — run scripts/simulate_room.py first")
    train = SpatialDataset.load(data / "train.npz")
    test = SpatialDataset.load(data / "test.npz")
    models = Path(cfg.model_dir)

    print(f"== data ==  train {len(train)} | test {len(test)} | "
          f"backend CNN: torch/sklearn auto\n")

    # --- Phase 1: single obstacle detection (one link) ---------------
    p1 = Phase1Detector(cfg, link=0).fit(train)
    e1 = p1.evaluate(test)
    p1.save(models / "phase1.pkl")
    print("Phase 1 — single obstacle detection (1 link)")
    print(f"   presence acc {e1.presence_acc:.3f} | "
          f"loc error {e1.loc_error_m:.2f} m\n")

    # --- Phase 2: multi-node sensing (all links) ---------------------
    p2 = Phase2Localizer(cfg).fit(train)
    e2 = p2.evaluate(test)
    p2.save(models / "phase2.pkl")
    print(f"Phase 2 — multi-node sensing ({cfg.n_rx} links)")
    print(f"   presence acc {e2.presence_acc:.3f} | "
          f"loc error {e2.loc_error_m:.2f} m")
    evn = error_vs_nodes(train, test, cfg)
    print("   localization error vs #nodes: "
          + ", ".join(f"{n}:{v:.2f}m" for n, v in evn.items()) + "\n")

    # --- Phase 3: room boundary estimation --------------------------
    ref = empty_room_reference(cfg, n_avg=64)
    b = evaluate_boundary(ref, cfg)
    rx0, ry0, rx1, ry1 = b["rect"]
    print("Phase 3 — room boundary estimation")
    print(f"   estimated room: {rx1-rx0:.2f} x {ry1-ry0:.2f} m "
          f"(true {cfg.room_w} x {cfg.room_h}) | IoU {b['iou']:.3f}")
    np.savez_compressed(models / "phase3_boundary.npz",
                        image=b["image"], xs=b["xs"], ys=b["ys"],
                        rect=np.array(b["rect"]), iou=b["iou"])
    print(f"\nsaved models -> {models}/phase1.pkl, phase2.pkl, "
          f"phase3_boundary.npz")


if __name__ == "__main__":
    main()
