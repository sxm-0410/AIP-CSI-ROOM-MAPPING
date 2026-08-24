"""End-to-end smoke tests for Phases 1-3 on synthetic data — no hardware.

Run:  python -m pytest -q     (or)     python tests/test_spatial.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from wifi_csi_spatial import load_config
from wifi_csi_spatial.capture.synthetic import (
    RoomSimulatorSource, empty_room_reference,
)
from wifi_csi_spatial.capture.router import parse_line
from wifi_csi_spatial.capture.esp32 import parse_esp_line
from wifi_csi_spatial.dataset import SpatialDataset
from wifi_csi_spatial.preprocessing import sanitize_phase, hampel
from wifi_csi_spatial.geometry.room import (
    localization_cell, cell_center, rect_iou, subcarrier_freqs,
)
from wifi_csi_spatial.phases import (
    Phase1Detector, Phase2Localizer, evaluate_boundary,
)


def _fast_cfg():
    cfg = load_config()
    cfg.n_subcarriers = 192
    cfg.cnn_epochs = 14
    cfg.pca_components = 64
    return cfg


def _dataset(cfg, n, seed, p_empty=0.2):
    src = RoomSimulatorSource(cfg, moving=False, seed=seed)
    rng = np.random.default_rng(seed + 1)
    csis, labels, xys = [], [], []
    for _ in range(n):
        if rng.random() < p_empty:
            obs, lab, xy = None, cfg.n_cells, (np.nan, np.nan)
        else:
            obs = (rng.uniform(0.3, cfg.room_w - 0.3),
                   rng.uniform(0.3, cfg.room_h - 0.3))
            lab, xy = localization_cell(obs, cfg), obs
        csis.append(src.sample(obs).csi)
        labels.append(lab)
        xys.append(xy)
    return SpatialDataset(np.stack(csis), np.array(labels),
                          np.array(xys, float), cfg.n_cells)


def test_phase_sanitization():
    cfg = _fast_cfg()
    freqs = subcarrier_freqs(cfg.n_subcarriers)
    from wifi_csi_spatial.geometry.room import Room, synth_csi
    room = Room.from_config(cfg)
    csi = synth_csi(room.link_paths(room.rx[0], (2.0, 2.0)), freqs)
    k = np.arange(cfg.n_subcarriers)
    tilted = csi * np.exp(2j * np.pi * 0.03 * k)      # inject CFO
    clean = sanitize_phase(tilted)
    assert np.allclose(np.abs(tilted), np.abs(clean), atol=1e-3)  # amp kept
    assert abs(np.angle(clean).mean()) < 0.3                       # tilt gone


def test_hampel_axis():
    x = np.ones((3, 40))
    x[1, 20] = 40.0
    out = hampel(x, window=4, n_sigma=3, axis=-1)
    assert out[1, 20] < 5.0


def test_parsers():
    r = parse_line("1.0,2,-45,1.0,0.5,2.0,-1.0")
    assert r is not None and r[1] == 2 and r[2].shape[0] == 2
    e = parse_esp_line("CSI_DATA,7,aa,-52,11,[1,2,3,4]")
    assert e is not None and e.shape[0] == 2


def test_geometry_roundtrip():
    cfg = _fast_cfg()
    c = localization_cell((3.1, 1.2), cfg)
    x, y = cell_center(c, cfg)
    assert localization_cell((x, y), cfg) == c
    assert rect_iou((0, 0, 5, 4), (0, 0, 5, 4)) == 1.0


def test_phase1_and_phase2_multinode_helps():
    cfg = _fast_cfg()
    train = _dataset(cfg, 800, seed=1)
    test = _dataset(cfg, 300, seed=99)

    p1 = Phase1Detector(cfg, link=0).fit(train).evaluate(test)
    p2 = Phase2Localizer(cfg).fit(train).evaluate(test)

    assert p1.presence_acc > 0.75
    assert p2.presence_acc > 0.90
    # multi-node localization clearly beats chance (~1.47 m in this room)...
    assert p2.loc_error_m < 1.2
    # ...and fusing nodes does not hurt vs a single link (usually much better)
    assert p2.loc_error_m <= p1.loc_error_m + 0.15


def test_phase3_boundary_iou():
    cfg = _fast_cfg()
    ref = empty_room_reference(cfg, n_avg=48, seed=3)
    res = evaluate_boundary(ref, cfg)
    assert res["iou"] > 0.5, res["rect"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
    print("all tests passed")
