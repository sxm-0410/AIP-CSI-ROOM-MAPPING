# Progress Status — Phases 1-3 complete

Rebuilt around the **Review-1 roadmap** (spatial mapping, not just occupant
zones). Signal source is a **Wi-Fi router**; ESP32-S3 nodes are stubbed for a
drop-in swap. Everything below runs end-to-end on the synthetic room simulator
and is exercised by `tests/test_spatial.py`.

## Architecture in place (Review-1 slide 3)

- Multi-node capture (`capture/`): router (current), esp32 (stub), synthetic
  simulator — one `Snapshot` = CSI for all TX→RX links at an instant.
- Cleaning (`preprocessing/`): CFO/SFO phase sanitization, Hampel outlier
  rejection, Butterworth low-pass, PCA reduction.
- Model (`models/cnn1d.py`): PyTorch 1D-CNN on PCA features (sklearn fallback).
- Serving (`api/server.py` + `web/index.html`): FastAPI + WebSocket → HTML5
  Canvas floor-map.

## Phase 1 — Single obstacle detection ✅

One TX→RX link → presence + coarse grid-cell localization via the
Butterworth→PCA→1D-CNN pipeline (`phases/phase1_obstacle.py`). Establishes the
single-link baseline (and its 2D ambiguity).

## Phase 2 — Multi-node sensing ✅

Fuses all links (`phases/phase2_multinode.py`). `error_vs_nodes` sweeps 1→N
nodes and reports localization error dropping as nodes are added — the concrete
multi-node result. Same code as Phase 1 with a wider fan-in.

## Phase 3 — Room boundary estimation ✅

Ellipse back-projection tomography (`phases/phase3_boundary.py`):
delay pseudo-spectrum per link → back-project onto the room grid at each cell's
reflection delay → walls reinforce → bounding box → **IoU vs true room**.
Uses a CFO-calibrated empty-room reference scan.

## Verified end-to-end

`simulate_room.py → train.py → uvicorn api.server` runs clean; the test suite
asserts Phase-1 presence detection beats chance, multi-node does not hurt (and
generally improves) localization, and Phase-3 boundary IoU clears threshold.

## Next (Phases 4-5)

- Phase 4: fit full room polygons / stitch multiple boundary scans into a floor
  plan (not just a bounding rectangle).
- Phase 5: real-time streaming inference on live ESP32-S3 nodes.
