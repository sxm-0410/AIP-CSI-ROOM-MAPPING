#!/usr/bin/env python3
"""Generate a synthetic multi-session, multi-zone dataset.

Lets the full pipeline (and the LOSO evaluation) run with no hardware — the
"data collection" stage from the roadmap, faked convincingly enough to exercise
every downstream stage. Replace with real router captures via ``scripts/capture.py``.

    python scripts/make_demo_data.py --sessions 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from csi_mapping import load_config
from csi_mapping.capture.synthetic import SyntheticSource, stable_seed
from csi_mapping.capture.base import collect_session
from csi_mapping.data.storage import Session, save_session


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--sessions", type=int, default=3,
                    help="captures per zone")
    ap.add_argument("--frames", type=int, default=1500,
                    help="frames per session")
    args = ap.parse_args()

    cfg = load_config()
    out = Path(cfg.data_dir)
    n = 0
    for zone in cfg.zone_names:
        for s in range(args.sessions):
            src = SyntheticSource(cfg, zone=zone,
                                  seed=1000 * s + stable_seed(zone) % 97)
            ts, csi = collect_session(src, args.frames)
            sid = f"{zone}_s{s:02d}"
            save_session(Session(sid, zone, ts, csi), out)
            n += 1
            print(f"  saved {sid}  ({csi.shape[0]} frames x "
                  f"{csi.shape[1]} subcarriers)")
    print(f"\n{n} sessions written to {out}/")


if __name__ == "__main__":
    main()
