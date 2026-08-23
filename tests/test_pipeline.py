"""End-to-end smoke tests on synthetic data — no hardware, no network.

Run:  python -m pytest -q     (or)     python tests/test_pipeline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from csi_mapping import load_config
from csi_mapping.capture.synthetic import SyntheticSource, stable_seed
from csi_mapping.capture.base import collect_session
from csi_mapping.capture.router import parse_csv_line
from csi_mapping.capture.esp32 import parse_esp_line
from csi_mapping.data.storage import Session
from csi_mapping.preprocessing import sanitize_phase, hampel
from csi_mapping.pipeline import frames_to_features
from csi_mapping.evaluation import leave_one_session_out


def _make_sessions(cfg, n_per_zone=2, frames=800):
    sessions = []
    for zone in cfg.zone_names:
        for s in range(n_per_zone):
            src = SyntheticSource(cfg, zone=zone,
                                  seed=17 * s + stable_seed(zone) % 91)
            ts, csi = collect_session(src, frames)
            sessions.append(Session(f"{zone}_s{s}", zone, ts, csi))
    return sessions


def test_phase_sanitization_removes_linear_tilt():
    cfg = load_config()
    src = SyntheticSource(cfg, zone="desk", seed=0)
    _, csi = collect_session(src, 50)
    cleaned = sanitize_phase(csi)
    # after detrending, mean phase per frame should sit near zero
    assert np.abs(np.angle(cleaned).mean()) < 0.2
    # amplitude is preserved
    assert np.allclose(np.abs(csi), np.abs(cleaned), atol=1e-4)


def test_hampel_removes_outliers():
    x = np.ones(100)
    x[50] = 50.0
    out = hampel(x, window=5, n_sigma=3)
    assert out[50] < 5.0


def test_router_and_esp_parsers():
    f = parse_csv_line("1.23,-45,1.0,0.5,2.0,-1.0")
    assert f is not None and f.n_subcarriers == 2
    assert np.isclose(f.rssi, -45)
    e = parse_esp_line('CSI_DATA,7,aa:bb,-52,11,...,[1,2,3,4]')
    assert e is not None and e.n_subcarriers == 2


def test_features_shape():
    cfg = load_config()
    src = SyntheticSource(cfg, zone="door", seed=3)
    _, csi = collect_session(src, cfg.window * 3)
    X = frames_to_features(csi, cfg)
    assert X.ndim == 2 and X.shape[0] >= 1
    assert X.shape[1] == 3 * cfg.n_subcarriers + 2


def test_loso_beats_chance():
    cfg = load_config()
    sessions = _make_sessions(cfg)
    report = leave_one_session_out(sessions, cfg)
    chance = 1.0 / len(cfg.zone_names)
    assert report.accuracy > chance + 0.15, report


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
