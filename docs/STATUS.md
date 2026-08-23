# Progress Status — Review 2

Snapshot of what runs today against the four-step roadmap. Signal source is a
**Wi-Fi router**; the ESP32 path is stubbed for a later, drop-in swap.

## Milestone: live CSI capture works

- CSI frames captured from the router and standardised into a single
  `CSIFrame` type (`capture/base.py`).
- Same interface already implemented for ESP32 USB-serial (`capture/esp32.py`)
  and for a synthetic generator used for offline runs and tests.
- **Why USB/serial, not Wi-Fi streaming for the ESP32 later:** the ESP32 has a
  single radio — streaming out over Wi-Fi would compete with the sensing radio
  and corrupt the very signal we measure. USB keeps sensing clean. The router
  backend sidesteps this by logging on the AP itself.

## Step 1 — Clean the signal  ✅ implemented

| piece | file | note |
|-------|------|------|
| Phase sanitization (CFO/SFO) | `preprocessing/phase.py` | per-frame linear phase detrend |
| Hampel outlier rejection | `preprocessing/filters.py` | median/MAD, along time |
| Butterworth low-pass | `preprocessing/filters.py` | SciPy `filtfilt`, EMA fallback |

## Step 2 — Collect & extract  ✅ pipeline ready, 🟡 real data pending

- Session storage across zones/sessions (`data/storage.py`, compact `.npz`).
- Windowed feature extraction (`features/extract.py`): per-subcarrier amplitude
  mean/std, phase std, temporal variance, total power.
- **Open item:** collect multi-session *real* router captures per zone.

## Step 3 — Model & validate  ✅ baseline in place

- XGBoost baseline with sklearn HistGradientBoosting fallback
  (`models/baseline.py`).
- Leave-one-session-out validation with confusion matrix
  (`evaluation/validate.py`) — the realistic, no-leakage score.
- **Next:** CNN / BiLSTM on raw windows behind the same `fit/predict` API.

## Step 4 — Live heatmap demo  ✅ working stand-in

- FastAPI service streams frames in a background thread, runs the shared
  transform on a rolling window, serves per-zone probabilities at `/heatmap`
  (`api/server.py`).
- Dependency-free web viewer (`web/index.html`); the roadmap's React front-end
  can consume the same endpoint later.

## Verified end-to-end

`make_demo_data.py → train.py → uvicorn api.server` runs clean, and
`tests/test_pipeline.py` asserts LOSO accuracy beats chance on synthetic data.
