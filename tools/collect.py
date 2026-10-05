#!/usr/bin/env python3
"""Guided data collection: stand in each zone when prompted.

    python tools/collect.py PORT --session day1_morning
    python tools/collect.py PORT --session day2 --seconds 40 --repeats 2

Record several sessions on different days/times: the model is evaluated on
held-out sessions, which is the honest test. Output: data/sessions/<session>.csv
"""
import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml.dataset import save_session
from ml.source import serial_frames


def record(frames, zone, seconds, now=time.monotonic):
    """Collect frames for ``seconds`` -> list of (zone, ms, rssi, amp)."""
    rows, end = [], now() + seconds
    for ms, rssi, amp in frames:
        rows.append((zone, ms, rssi, amp))
        if now() >= end:
            break
    return rows


def drain(frames, seconds, now=time.monotonic):
    """Keep reading (and discarding) for ``seconds``, so the serial backlog from
    the walk to your spot is not recorded as the zone."""
    end = now() + seconds
    for _ in frames:
        if now() >= end:
            break


def load_zone_names(path="config/zones.yaml"):
    import yaml
    return list(yaml.safe_load(Path(path).read_text())["zones"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("--session", default=time.strftime("%Y%m%d_%H%M"))
    ap.add_argument("--seconds", type=float, default=30)
    ap.add_argument("--rest", type=float, default=5, help="get-into-position time")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--zones", default="config/zones.yaml")
    args = ap.parse_args()

    plan = ["empty"] + load_zone_names(args.zones)
    frames = serial_frames(args.port, args.baud)
    rows = []
    for rep in range(args.repeats):
        for zone in plan:
            who = "LEAVE the room" if zone == "empty" else f"stand in zone {zone}"
            print(f"\n[{rep + 1}/{args.repeats}] {who} — recording in {args.rest:.0f}s")
            drain(frames, args.rest)
            got = record(frames, zone, args.seconds)
            rows += got
            print(f"  {zone}: {len(got)} frames")
    out = Path("data/sessions") / f"{args.session}.csv"
    save_session(out, rows)
    print("saved", out)


if __name__ == "__main__":
    main()
