#!/usr/bin/env python3
"""Live spatial-mapping demo  (FastAPI + WebSockets, per the deck).

Streams, over a WebSocket, the room the system currently "sees":
  * the Phase-3 estimated room boundary,
  * a Phase-2 obstacle-location heatmap over the grid,
  * the live obstacle estimate vs ground truth.

    uvicorn api.server:app          # then open http://127.0.0.1:8000

The visualization is a dependency-free HTML5 Canvas (the deck's React dashboard
can consume the same /ws feed later).
"""
from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse

from wifi_csi_spatial import load_config
from wifi_csi_spatial.capture.synthetic import RoomSimulatorSource
from wifi_csi_spatial.phases import Phase2Localizer

cfg = load_config()
app = FastAPI(title="Wi-Fi CSI Spatial Mapping")

_state: dict = {"snapshot": None}
_lock = threading.Lock()
_loc: Phase2Localizer | None = None
_boundary = {"rect": [0, 0, cfg.room_w, cfg.room_h], "iou": None}


def _load_artifacts():
    global _loc
    m = Path(cfg.model_dir)
    try:
        from wifi_csi_spatial.phases import Localizer
        _loc = Localizer.load(m / "phase2.pkl")
    except FileNotFoundError:
        _loc = None
    bpath = m / "phase3_boundary.npz"
    if bpath.exists():
        with np.load(bpath) as z:
            _boundary["rect"] = z["rect"].tolist()
            _boundary["iou"] = float(z["iou"])


def _capture_loop():
    src = RoomSimulatorSource(cfg, moving=True, seed=7)
    import time
    for snap in src.snapshots():
        with _lock:
            _state["snapshot"] = snap
        time.sleep(1.0 / cfg.sample_rate_hz)


@app.on_event("startup")
def _startup():
    _load_artifacts()
    threading.Thread(target=_capture_loop, daemon=True).start()


def _current_state() -> dict:
    with _lock:
        snap = _state["snapshot"]
    out = {
        "room": {"w": cfg.room_w, "h": cfg.room_h},
        "nodes": {"tx": list(cfg.tx), "rx": [list(p) for p in cfg.rx]},
        "grid": {"rows": cfg.grid_rows, "cols": cfg.grid_cols},
        "boundary": _boundary,
        "ready": False,
    }
    if snap is None:
        out["error"] = "warming up"
        return out
    out["truth"] = None if snap.obstacle is None else list(snap.obstacle)
    if _loc is None:
        out["error"] = "no model — run scripts/train.py"
        return out
    est = _loc.predict(snap.csi)
    out.update(ready=True, grid_probs=_loc.heatmap(snap.csi), estimate={
        "present": est["present"],
        "xy": list(est["xy"]) if est["xy"] else None,
        "confidence": est["confidence"],
    })
    return out


@app.get("/state")
def state() -> JSONResponse:
    return JSONResponse(_current_state())


@app.websocket("/ws")
async def ws(sock: WebSocket):
    await sock.accept()
    try:
        while True:
            await sock.send_json(_current_state())
            await asyncio.sleep(0.2)
    except WebSocketDisconnect:
        pass


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "web" / "index.html")
