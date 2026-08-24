# Wi-Fi CSI Spatial Mapping

Reconstruct indoor spatial information from Wi-Fi **Channel State Information
(CSI)** — a low-cost, privacy-preserving alternative to LiDAR and cameras. CSI
carries the amplitude and phase of every OFDM subcarrier, so the multipath
reflections in a room encode its geometry. This repo turns that signal into
obstacle locations and a room outline.

```
capture (multi-node) -> clean (CFO/SFO + Butterworth) -> PCA -> 1D-CNN / tomography -> live map
```

> **Status.** Roadmap Phases **1-3 are implemented and run end-to-end**. Signal
> comes from a **Wi-Fi router** today; the **ESP32-S3** backend is stubbed for a
> one-line switch later.

## Roadmap (from Review 1) — where we are

| Phase | Goal | Status |
|------:|------|--------|
| 1 | Single obstacle detection | ✅ `phases/phase1_obstacle.py` |
| 2 | Multi-node sensing | ✅ `phases/phase2_multinode.py` |
| 3 | Room boundary estimation | ✅ `phases/phase3_boundary.py` |
| 4 | Automatic floor-plan generation | ⏳ next |
| 5 | Real-time spatial intelligence | ⏳ next |

## What each phase does

- **Phase 1 — Single obstacle detection.** From **one** TX→RX link, decide if an
  obstacle is present and which coarse grid cell it's in. A single link is
  inherently ambiguous in 2D — that's the motivation for Phase 2.
- **Phase 2 — Multi-node sensing.** Fuse **all** TX→RX links. Independent
  viewpoints resolve the ambiguity, so localization error drops. `error_vs_nodes`
  reports accuracy as node count grows — the headline result.
- **Phase 3 — Room boundary estimation.** Invert the empty-room multipath into a
  floor outline by **ellipse back-projection**: each link's path-length spectrum
  is back-projected onto the room grid; wall reflections reinforce where links
  agree, tracing the walls. Scored by IoU against the true room.

Phases 1-2 follow the deck's stack exactly: **noise filtering (Butterworth) →
feature reduction (PCA) → 1D-CNN** (PyTorch, with an sklearn fallback).

## Quickstart (no hardware needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. simulate a room dataset (multi-node CSI across obstacle positions)
python scripts/simulate_room.py --train 2500 --test 800

# 2. train + evaluate all three phases, save models
python scripts/train.py

# 3. live demo (FastAPI + WebSocket), then open http://127.0.0.1:8000
uvicorn api.server:app
```

Tests:

```bash
python -m pytest -q          # or: python tests/test_spatial.py
```

### With a real Wi-Fi router

Set `backend: router` in [config.yaml](config.yaml) and point `router_source` at
your CSI tool's CSV log or a `udp://host:port` stream (one line per link:
`timestamp,rx_id,rssi,re0,im0,...`). Then:

```bash
python scripts/capture.py --cell 5 --frames 500     # obstacle in grid cell 5
python scripts/capture.py --empty  --frames 500     # empty-room boundary scan
python scripts/train.py
```

Moving to ESP32-S3 nodes later is just `backend: esp32` (+ `pyserial`) — no
pipeline changes.

## Architecture (matches Review-1 slide 3)

```
ESP32/Router TX -> multipath -> RX nodes (CSI) -> WebSocket -> pipeline -> dashboard
```

```
wifi_csi_spatial/
  geometry/      room model + multipath physics (shared by sim, Phase 3, viz)
  capture/       router (now) · esp32 (later) · synthetic — one Snapshot interface
  preprocessing/ CFO/SFO phase sanitization · Hampel + Butterworth · PCA
  features/      per-link amplitude/phase, stacked across nodes
  models/        1D-CNN (PyTorch, sklearn fallback)
  phases/        phase1 · phase2 (+ error_vs_nodes) · phase3 boundary tomography
  dataset.py     labelled multi-node sample storage
scripts/         simulate_room · train · capture
api/ + web/      FastAPI + WebSocket · HTML5 Canvas floor-map viewer
tests/           end-to-end smoke tests
```

## Design notes

- **Backend-agnostic capture.** Router, ESP32, and simulator all yield the same
  `Snapshot` (CSI for every link at one instant); nothing downstream branches on
  hardware.
- **Runs anywhere.** Torch→sklearn and SciPy→EMA fallbacks keep the core working
  even without the heavy deps.
- **Honest geometry.** The simulator and Phase 3 share one `Room` model, so the
  reconstruction is scored against exactly the layout that produced the signal.
- **Physics, not magic.** Phase 3 assumes a one-time CFO-calibrated empty-room
  scan — a raw per-frame offset is indistinguishable from a real delay, so we
  calibrate before boundary mapping (standard practice). Resolution scales with
  bandwidth and node geometry.

See [`docs/STATUS.md`](docs/STATUS.md) for the detailed progress breakdown.
