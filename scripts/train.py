#!/usr/bin/env python3
"""Validate with LOSO, then fit the final model on everything.

    python scripts/train.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from csi_mapping import load_config
from csi_mapping.data.storage import load_dataset
from csi_mapping.evaluation import leave_one_session_out
from csi_mapping.models import ZoneClassifier
from csi_mapping.pipeline import build_dataset


def main() -> None:
    cfg = load_config()
    sessions = load_dataset(cfg.data_dir)
    if not sessions:
        raise SystemExit(
            f"no sessions in {cfg.data_dir}/. Run scripts/make_demo_data.py "
            f"or scripts/capture.py first."
        )
    print(f"loaded {len(sessions)} sessions across "
          f"{len({s.zone for s in sessions})} zones\n")

    report = leave_one_session_out(sessions, cfg)
    print(report)
    print("\nconfusion matrix (rows=true, cols=pred):")
    print("labels:", report.labels)
    print(report.confusion)

    # final model on all data
    X, y, _ = build_dataset(sessions, cfg)
    clf = ZoneClassifier().fit(X, y)
    path = clf.save(cfg.model_path)
    print(f"\nbackend: {clf.backend}")
    print(f"final model trained on {len(X)} windows -> {path}")


if __name__ == "__main__":
    main()
