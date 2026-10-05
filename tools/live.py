#!/usr/bin/env python3
"""Live zone map from the ESP32 (or replay a recording).

    python tools/live.py --port PORT --model models/zone_model.joblib
    python tools/live.py --replay data/sessions/day1.csv --model models/zone_model.joblib
    add --plot for a heatmap window laid out per config/zones.yaml
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from ml.live import ZonePredictor
from ml.source import replay_frames, serial_frames


def grid_from_probs(probs, zones_cfg):
    g = zones_cfg["grid"]
    img = np.zeros((g["rows"], g["cols"]))
    for name, z in zones_cfg["zones"].items():
        r, c = z["pos"]
        img[r, c] = probs.get(name, 0.0)
    return img


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port")
    ap.add_argument("--replay")
    ap.add_argument("--model", default="models/zone_model.joblib")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--zones", default="config/zones.yaml")
    ap.add_argument("--plot", action="store_true")
    ap.add_argument("--speed", type=float, default=0, help="replay frames/s (0=fast)")
    args = ap.parse_args()
    if bool(args.port) == bool(args.replay):
        sys.exit("give exactly one of --port / --replay")

    import joblib
    import yaml
    pred = ZonePredictor(joblib.load(args.model))
    cfg = yaml.safe_load(Path(args.zones).read_text())
    frames = (serial_frames(args.port, args.baud) if args.port
              else replay_frames(args.replay))
    if args.plot:
        import matplotlib.pyplot as plt
        plt.ion()
        _, ax = plt.subplots()
        im = ax.imshow(np.zeros((cfg["grid"]["rows"], cfg["grid"]["cols"])),
                       vmin=0, vmax=1, cmap="viridis")
        ttl = ax.set_title("")
        for n, z in cfg["zones"].items():
            ax.text(z["pos"][1], z["pos"][0], n, ha="center", va="center", color="w")
    try:
        for _, _, amp in frames:
            res = pred.push(amp)
            if args.speed:
                time.sleep(1 / args.speed)
            if res is None:
                continue
            top = ", ".join(f"{k}={v:.2f}" for k, v in
                            sorted(res["probs"].items(), key=lambda kv: -kv[1])[:3])
            print(f"\rzone={res['zone']:8s} {top:40s}", end="", flush=True)
            if args.plot:
                im.set_data(grid_from_probs(res["probs"], cfg))
                ttl.set_text("empty" if res["zone"] == "empty" else f"zone {res['zone']}")
                plt.pause(0.001)
    except KeyboardInterrupt:
        pass
    print()


if __name__ == "__main__":
    main()
