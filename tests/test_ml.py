"""No-hardware tests for the CSI -> zone pipeline.  Run:  python -m pytest -q tests"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from ml import preprocess as pp
from ml.csi import parse_csi_line
from ml.dataset import load_session, save_session
from ml.live import ZonePredictor
from ml.source import replay_frames
from ml.synth import make_session
from ml.train import evaluate, train_final

ZONES = ["empty", "A", "B", "C"]


def test_parse_our_format_and_garbage():
    ms, rssi, amp = parse_csi_line("CSI_DATA,3,1200,-47,8,[83,-80,4,0,3,4,-6,8]")
    assert (ms, rssi) == (1200, -47)
    assert np.allclose(amp, [5, 10])                       # junk first 2 pairs dropped; hypot of the rest
    assert parse_csi_line("MOTION,1,2,3,4") is None
    assert parse_csi_line("CSI_DATA,1,2,-40,4,[1,2,x]") is None
    parse_csi_line("CSI_DATA,1,2,-40,4,[1,2")              # truncated line: must not raise


def test_hampel_removes_spike_and_mask_drops_dead_tone():
    x = np.full((50, 8), 10.0, dtype=np.float32)
    x[20, 3] = 500
    assert pp.hampel_time(x)[20, 3] == 10.0
    x[:, 0] = 0
    assert not pp.active_mask(x)[0]


def test_session_roundtrip(tmp_path):
    s = make_session(ZONES, seconds=2, seed=1)
    rows = [(z, i, -40, a) for z, amps in s.items() for i, a in enumerate(amps)]
    save_session(tmp_path / "s.csv", rows)
    back = load_session(tmp_path / "s.csv")
    assert set(back) == set(ZONES) and back["A"].shape == s["A"].shape


def test_held_out_session_beats_majority_baseline():
    sessions = [make_session(ZONES, seconds=20, seed=s) for s in range(3)]
    acc, base, cm, classes = evaluate(sessions)
    assert base == 0.25 or abs(base - 0.25) < 0.05
    assert acc > 0.9, (acc, cm)


def test_live_predictor_and_replay(tmp_path):
    train = [make_session(ZONES, seconds=20, seed=s) for s in range(3)]
    pred = ZonePredictor(train_final(train))
    new = make_session(ZONES, seconds=10, seed=9)
    rows = [(z, i, -40, a) for z, amps in new.items() for i, a in enumerate(amps)]
    save_session(tmp_path / "r.csv", rows)
    hits = {z: [] for z in ZONES}
    zone_of = [r[0] for r in rows]
    for i, (_, _, amp) in enumerate(replay_frames(tmp_path / "r.csv")):
        res = pred.push(amp)
        if res:
            hits[zone_of[i]].append(res["zone"])
    for z in ZONES:                       # second half of each zone: smoothing has settled
        tail = hits[z][len(hits[z]) // 2:]
        assert np.mean([t == z for t in tail]) > 0.8, (z, tail)


def test_wrong_length_frame_ignored():
    train = [make_session(ZONES, seconds=10, seed=s) for s in range(2)]
    pred = ZonePredictor(train_final(train))
    assert pred.push(np.zeros(10, dtype=np.float32)) is None


def test_collect_drain_discards_rest_period_then_records():
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools"))
    from collect import drain, record
    t = [0.0]

    def clock():
        t[0] += 0.1
        return t[0]
    frames = ((i, -40, np.ones(4, np.float32) * i) for i in range(10_000))
    drain(frames, 5.0, now=clock)             # ~50 frames discarded
    rows = record(frames, "A", 1.0, now=clock)
    assert 5 <= len(rows) <= 15
    assert rows[0][1] >= 40                    # none of the rest-period frames kept


def test_serial_lines_chunked_reader_handles_splits_and_timeouts():
    from ml.source import serial_lines

    class Fake:
        def __init__(self, chunks):
            self.chunks, self.in_waiting = list(chunks), 0

        def read(self, n):
            return self.chunks.pop(0) if self.chunks else b""

    ser = Fake([b"CSI_DATA,1,", b"2,-40,4,[1,2]\nMOTION,5,-4", b"0,1.0,1\n", b"", b"tail\n"])
    got = []
    for ln in serial_lines(ser):
        got.append(ln)
        if len(got) == 4:
            break
    assert got == ["CSI_DATA,1,2,-40,4,[1,2]", "MOTION,5,-40,1.0,1", "", "tail"]
