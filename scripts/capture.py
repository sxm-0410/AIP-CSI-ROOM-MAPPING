#!/usr/bin/env python3
"""Capture one labelled session from the configured backend.

    # from the router (current)
    python scripts/capture.py --zone desk --frames 1500

    # once on ESP32, only the config/flag changes:
    python scripts/capture.py --zone desk --backend esp32
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from csi_mapping import load_config
from csi_mapping.capture import open_source, collect_session
from csi_mapping.data.storage import Session, save_session


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zone", required=True, help="ground-truth zone label")
    ap.add_argument("--frames", type=int, default=1500)
    ap.add_argument("--backend", default=None,
                    help="override config backend: router|esp32|synthetic")
    ap.add_argument("--id", default=None, help="session id (default: zone+time)")
    args = ap.parse_args()

    cfg = load_config()
    if args.backend:
        cfg.backend = args.backend

    sid = args.id or f"{args.zone}_{int(time.time())}"
    print(f"capturing {args.frames} frames from '{cfg.backend}' "
          f"backend for zone '{args.zone}'...")
    with open_source(cfg, zone=args.zone) as src:
        ts, csi = collect_session(src, args.frames)
    path = save_session(Session(sid, args.zone, ts, csi), cfg.data_dir)
    print(f"saved {path}  ({csi.shape[0]} x {csi.shape[1]})")


if __name__ == "__main__":
    main()
