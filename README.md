# Wi-Fi CSI Room Mapping

Infer **which zone of a room a person is in** from Wi-Fi Channel State
Information (CSI) — no cameras, no wearables. The pipeline turns raw CSI into a
live occupant-zone heatmap:

```
capture  ->  clean  ->  features  ->  model  ->  live heatmap
```

> **Status — Progress Review 2.** Live CSI capture is working and the full
> pipeline runs end-to-end on data. Signal is captured from a **Wi-Fi router**
> today; the **ESP32** backend is already stubbed so the switch later is a
> one-line config change. Currently in the *data collection* stage.

---

## Why the capture backend is swappable

The signal source is the only part of a CSI project that depends on hardware.
Everything downstream (cleaning, features, model, demo) is identical whether the
bytes come from a router or an ESP32. So capture is a single interface:

```python
class CSISource:          # csi_mapping/capture/base.py
    def frames(self) -> Iterator[CSIFrame]: ...
```

| backend      | file                        | status            |
|--------------|-----------------------------|-------------------|
| `router`     | `capture/router.py`         | **current**       |
| `esp32`      | `capture/esp32.py`          | stubbed for later |
| `synthetic`  | `capture/synthetic.py`      | offline dev/demo  |

Switching hardware later = `backend: esp32` in `config.yaml`. No pipeline edits.

---

## Quickstart (no hardware needed)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1. generate a synthetic multi-session dataset (stands in for real captures)
python scripts/make_demo_data.py --sessions 3

# 2. validate (leave-one-session-out) + train the final model
python scripts/train.py

# 3. run the live heatmap demo, then open http://127.0.0.1:8000
uvicorn api.server:app
```

Run the tests:

```bash
python -m pytest -q          # or: python tests/test_pipeline.py
```

### Capturing real data from the router

```bash
# point config.router_source at your CSV log or a udp://host:port stream,
# then set backend: router in config.yaml
python scripts/capture.py --zone desk   --frames 1500
python scripts/capture.py --zone empty  --frames 1500
python scripts/train.py
```

The router logger just needs to emit one line per frame:
`timestamp,rssi,re0,im0,re1,im1,...` (see `capture/router.py`).

---

## How it maps to the roadmap

| Review-2 roadmap step        | Where it lives                                   |
|------------------------------|--------------------------------------------------|
| 1. Clean the signal          | `preprocessing/phase.py` (CFO/SFO), `filters.py` (Hampel → Butterworth) |
| 2. Collect & extract         | `data/storage.py` (sessions), `features/extract.py` |
| 3. Model & validate          | `models/baseline.py` (XGBoost), `evaluation/validate.py` (LOSO) |
| 4. Live heatmap demo         | `api/server.py` (FastAPI) + `web/index.html`     |

See [`docs/STATUS.md`](docs/STATUS.md) for the detailed progress breakdown.

---

## Project layout

```
csi_mapping/
  capture/       router (now) · esp32 (later) · synthetic — one interface
  preprocessing/ phase sanitization, Hampel + Butterworth
  features/      windowed amplitude/phase features
  models/        XGBoost baseline (sklearn fallback)
  evaluation/    leave-one-session-out validation
  pipeline.py    capture/session -> features (shared by train & serve)
scripts/         make_demo_data · capture · train
api/ + web/      FastAPI heatmap service + viewer
tests/           end-to-end smoke tests on synthetic data
```

## Design notes

- **Runs anywhere.** XGBoost → sklearn and SciPy → EMA fallbacks mean the core
  pipeline works with just numpy if needed.
- **No train/serve skew.** Training and the live demo call the *same*
  `frames_to_features`.
- **Honest evaluation.** Leave-one-session-out holds out whole captures, so
  accuracy isn't inflated by correlated neighbouring windows.

## Roadmap

- [x] Live CSI capture (router) + USB/serial-clean path
- [x] Phase sanitization + amplitude denoising
- [x] Feature extraction + XGBoost baseline + LOSO
- [x] FastAPI + web live heatmap
- [ ] Multi-session real-world data collection across zones
- [ ] CNN / BiLSTM model on raw windows
- [ ] ESP32 backend on real hardware
