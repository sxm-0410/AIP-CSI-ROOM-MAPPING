#!/usr/bin/env python3
"""Read the ESP32's serial output, show live status and log to CSV.

    python tools/monitor.py /dev/cu.usbserial-0001            # log + status
    python tools/monitor.py /dev/cu.usbserial-0001 --plot     # + live RSSI plot

Lines look like  MOTION,<ms>,<rssi>,<std>,<state>   (state 0=calibrating 1=idle 2=motion).
"""
import argparse
import csv
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.source import serial_lines  # noqa: E402

STATES = {0: "calibrating", 1: "idle", 2: "MOTION"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--out", default=f"logs/run_{time.strftime('%Y%m%d_%H%M%S')}.csv")
    ap.add_argument("--plot", action="store_true")
    args = ap.parse_args()

    try:
        import serial
    except ImportError:
        sys.exit("pip install -r requirements.txt")

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    hist = []
    if args.plot:
        import matplotlib.pyplot as plt
        plt.ion()
        fig, ax = plt.subplots()
        line, = ax.plot([], [])
        ax.set_xlabel("sample"); ax.set_ylabel("RSSI (dBm)")

    with serial.Serial(args.port, args.baud, timeout=1) as ser, \
            open(args.out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["ms", "rssi", "std", "state"])
        fh.flush()
        print(f"logging to {args.out} — Ctrl-C to stop")
        last_ok, warned = time.monotonic(), False
        lines = serial_lines(ser)                  # chunked: readline() drops data at this speed
        try:
            while True:
                raw = next(lines).strip()
                k = raw.find("MOTION,")          # CSI and MOTION prints can splice together
                if k > 0:
                    raw = raw[k:]
                if not warned and time.monotonic() - last_ok > 5:
                    warned = True
                    print("\nno MOTION lines for 5 s — is the board running and flashed "
                          "with this firmware? is another program (idf.py monitor) "
                          f"using the port? baud={args.baud} must match the firmware.")
                if not raw.startswith("MOTION,"):
                    if raw and not raw.startswith("CSI_DATA"):   # CSI rows are for collect.py
                        print(raw)
                    continue
                try:
                    _, ms, rssi, std, st = raw.split(",")[:5]   # extra fields (thr, base, pct) ignored here
                    row = [int(ms), int(rssi), float(std), int(st)]
                except ValueError:
                    continue
                w.writerow(row)
                fh.flush()                       # visible on disk immediately
                last_ok, warned = time.monotonic(), False
                print(f"\r{STATES.get(row[3], '?'):12s} rssi={row[1]:4d} dBm  "
                      f"std={row[2]:5.2f}", end="", flush=True)
                if args.plot:
                    hist.append(row[1])
                    hist = hist[-300:]
                    if len(hist) % 5 == 0:
                        line.set_data(range(len(hist)), hist)
                        ax.relim(); ax.autoscale_view(); plt.pause(0.001)
        except KeyboardInterrupt:
            print()


if __name__ == "__main__":
    main()
