#!/usr/bin/env python3
"""Live dashboard for the ESP32 Wi-Fi path monitor.

    python -m ui.server --port /dev/cu.usbserial-110     # real board
    python -m ui.server --demo                           # simulated data (labelled in the UI)

Opens http://127.0.0.1:8000. The server owns the serial port, so close any other
monitor first.
"""
from __future__ import annotations

import argparse
import asyncio
import math
import random
import sys
import threading
import time
import webbrowser
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response

from ml.csi import parse_csi_line, parse_motion_line
from ml.source import serial_lines

STATIC = Path(__file__).resolve().parent / "static"
HISTORY = 600                       # motion samples kept for new clients (~60 s)


class Hub:
    """Thread-safe latest-state store shared by the reader thread and websockets."""

    def __init__(self, mode: str):
        self.mode = mode
        self.connected = False
        self.lock = threading.Lock()
        self.samples: deque = deque(maxlen=HISTORY)     # (seq, dict)
        self.seq = 0
        self.csi: list | None = None
        self._csi_times: deque = deque(maxlen=200)
        self.last_data = 0.0

    def feed_motion(self, d: dict) -> None:
        with self.lock:
            self.seq += 1
            self.samples.append((self.seq, d))
            self.last_data = time.monotonic()

    def feed_csi(self, amp) -> None:
        now = time.monotonic()
        with self.lock:
            self.csi = [round(float(a), 1) for a in amp]
            self._csi_times.append(now)
            self.last_data = now

    def csi_rate(self) -> float:
        now = time.monotonic()
        with self.lock:
            return float(sum(1 for t in self._csi_times if now - t <= 1.0))

    def since(self, cursor: int):
        with self.lock:
            return [d for s, d in self.samples if s > cursor], self.seq

    def snapshot(self) -> dict:
        with self.lock:
            stale = time.monotonic() - self.last_data > 3.0
            return {"mode": self.mode, "connected": self.connected and not stale,
                    "csi": self.csi}


hub: Hub = Hub("live")
app = FastAPI(title="Wi-Fi path monitor")


# ---------------------------------------------------------------- sources
def serial_reader(h: Hub, port: str, baud: int) -> None:
    try:
        import serial
    except ImportError:
        sys.exit("pip install -r requirements.txt")
    while True:
        try:
            with serial.Serial(port, baud, timeout=1) as ser:
                h.connected = True
                print(f"reading {port} @ {baud}")
                for line in serial_lines(ser):
                    if not line:
                        continue
                    if line.startswith("CSI_DATA"):
                        f = parse_csi_line(line)
                        if f is not None:
                            h.feed_csi(f[2])
                    elif "MOTION," in line:
                        d = parse_motion_line(line)
                        if d is not None:
                            h.feed_motion(d)
        except (OSError, serial.SerialException) as e:
            h.connected = False
            print(f"serial problem ({e}); retrying in 2 s — is another program using {port}?")
            time.sleep(2)


def demo_reader(h: Hub) -> None:
    """Scripted scenario: learn, clear, object crosses the path, clear, repeat."""
    h.connected = True
    rng = random.Random(3)
    base, thr, t0 = -42.0, 2.0, time.monotonic()
    shape = np.array([20 + 8 * math.sin(i / 7) + 4 * math.cos(i / 3) for i in range(62)])
    hold_until = 0.0
    last_motion = 0.0
    state = 0
    while True:
        t = time.monotonic() - t0
        ph = t % 44
        crossing = (16 <= ph < 23) or (31 <= ph < 36)
        learning = t < 8
        if crossing:
            hold_until = time.monotonic() + 1.5
        rssi = base + rng.gauss(0, 0.7)
        std = abs(rng.gauss(0.8, 0.12))
        if crossing:
            rssi -= 5 + 3 * math.sin(t * 3) + rng.gauss(0, 1.5)
            std = 3.0 + abs(rng.gauss(0, 0.7))
        state = 0 if learning else (2 if time.monotonic() < hold_until else 1)
        if time.monotonic() - last_motion >= 0.1:
            last_motion = time.monotonic()
            h.feed_motion({"t": int(t * 1000), "rssi": int(round(rssi)), "std": round(std, 2),
                           "state": state, "thr": thr, "base": base,
                           "pct": min(100, int(100 * t / 8)) if learning else 100})
        amp = shape + rng.gauss(0, 0.4)
        if crossing:
            amp = amp + 10 * np.sin(np.arange(62) / 4 + t * 6) * rng.uniform(0.4, 1.0) \
                - 4
        amp = amp + np.array([rng.gauss(0, 0.5) for _ in range(62)])
        h.feed_csi(np.clip(amp, 0, None))
        time.sleep(0.02)


# ---------------------------------------------------------------- web
@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/state")
def state() -> dict:
    s = hub.snapshot()
    s["csi_rate"] = hub.csi_rate()
    return s


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    cursor = 0                                   # new client gets the recent history
    try:
        while True:
            fresh, cursor = hub.since(cursor)
            msg = hub.snapshot()
            msg.update(samples=fresh, csi_rate=hub.csi_rate())
            await sock.send_json(msg)
            await asyncio.sleep(0.1)
    except (WebSocketDisconnect, RuntimeError):
        pass


def main() -> None:
    global hub
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", help="serial port, e.g. /dev/cu.usbserial-110")
    ap.add_argument("--baud", type=int, default=460800)
    ap.add_argument("--demo", action="store_true", help="simulated data (shown as DEMO in the UI)")
    ap.add_argument("--http-port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    if bool(args.port) == bool(args.demo):
        sys.exit("give exactly one of --port PORT / --demo")

    hub = Hub("demo" if args.demo else "live")
    target = (lambda: demo_reader(hub)) if args.demo else \
             (lambda: serial_reader(hub, args.port, args.baud))
    threading.Thread(target=target, daemon=True).start()

    url = f"http://127.0.0.1:{args.http_port}"
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"dashboard: {url}   (Ctrl-C to stop)")
    uvicorn.run(app, host="127.0.0.1", port=args.http_port, log_level="warning")


if __name__ == "__main__":
    main()
