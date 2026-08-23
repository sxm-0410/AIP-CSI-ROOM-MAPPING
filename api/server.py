#!/usr/bin/env python3
"""Live occupant-zone heatmap  (roadmap step 4: "Live heatmap demo").

A FastAPI service that:
  * pulls CSI frames from the configured backend in a background thread,
  * runs the exact training-time transform on a rolling window,
  * serves current per-zone probabilities as a grid at ``/heatmap``,
  * serves a tiny self-contained viewer at ``/``.

    uvicorn api.server:app --reload
    # then open http://127.0.0.1:8000

The React front-end from the roadmap can consume ``/heatmap`` as-is; the bundled
page is a dependency-free stand-in so the demo runs today.
"""
from __future__ import annotations

import sys
import threading
import time
from collections import deque
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse

from csi_mapping import load_config
from csi_mapping.capture import open_source
from csi_mapping.models import ZoneClassifier
from csi_mapping.pipeline import frames_to_features

cfg = load_config()
app = FastAPI(title="Wi-Fi CSI Room Mapping")

_buf: deque = deque(maxlen=cfg.window * 2)
_model: ZoneClassifier | None = None
_lock = threading.Lock()


def _load_model() -> ZoneClassifier | None:
    try:
        return ZoneClassifier.load(cfg.model_path)
    except FileNotFoundError:
        return None


def _capture_loop() -> None:
    """Background thread: continuously fill the rolling frame buffer."""
    src = open_source(cfg)
    # the synthetic source yields as fast as the CPU allows; pace it to the
    # sample rate so the demo doesn't peg a core. Real backends block on I/O.
    interval = 1.0 / cfg.sample_rate_hz if cfg.backend == "synthetic" else 0.0
    for frame in src.frames():
        with _lock:
            _buf.append(frame.csi)
        if interval:
            time.sleep(interval)


@app.on_event("startup")
def _startup() -> None:
    global _model
    _model = _load_model()
    threading.Thread(target=_capture_loop, daemon=True).start()


@app.get("/heatmap")
def heatmap() -> JSONResponse:
    """Current per-zone probability grid for the front-end to render."""
    with _lock:
        frames = list(_buf)
    grid = np.zeros((cfg.grid_rows, cfg.grid_cols)).tolist()
    payload = {
        "zones": [z.__dict__ for z in cfg.zones],
        "rows": cfg.grid_rows,
        "cols": cfg.grid_cols,
        "grid": grid,
        "predicted": None,
        "ready": False,
    }
    if _model is None:
        payload["error"] = "no trained model — run scripts/train.py"
        return JSONResponse(payload)
    if len(frames) < cfg.window:
        payload["error"] = f"warming up ({len(frames)}/{cfg.window} frames)"
        return JSONResponse(payload)

    csi = np.stack(frames[-cfg.window:])
    X = frames_to_features(csi, cfg)
    if len(X) == 0:
        return JSONResponse(payload)
    proba = _model.predict_proba(X).mean(axis=0)
    probs = dict(zip(_model.classes_, proba))
    for z in cfg.zones:
        grid[z.row][z.col] = float(probs.get(z.name, 0.0))
    payload.update(grid=grid, ready=True,
                   predicted=str(_model.classes_[int(np.argmax(proba))]))
    return JSONResponse(payload)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(Path(__file__).resolve().parent.parent / "web" / "index.html")
