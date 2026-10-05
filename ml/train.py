#!/usr/bin/env python3
"""Train a zone classifier from recorded sessions.

    python -m ml.train data/sessions/*.csv --out models/zone_model.joblib
    python -m ml.train --synthetic             # demo with no hardware

Evaluation is leave-one-session-out: train on all sessions but one, test on the
held-out one. Random packet splits leak neighbouring frames and badly overstate
accuracy, so they are not offered.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from ml import preprocess as pp
from ml.dataset import load_session
from ml.models import build


def build_xy(sessions, mask):
    X, y, g = [], [], []
    for gi, sess in enumerate(sessions):
        for zone, amps in sess.items():
            f = pp.make_windows(amps, mask)
            X.append(f); y += [zone] * len(f); g += [gi] * len(f)
    return np.concatenate(X), np.array(y), np.array(g)


def evaluate(sessions, kind="rf"):
    """Leave-one-session-out -> (accuracy, majority baseline, confusion, classes)."""
    from sklearn.metrics import confusion_matrix
    mask = pp.active_mask(np.concatenate([a for s in sessions for a in s.values()]))
    X, y, g = build_xy(sessions, mask)
    classes = sorted(str(c) for c in set(y))
    preds = np.empty_like(y)
    for gi in sorted(set(g)):
        tr, te = g != gi, g == gi
        m = build(kind).fit(X[tr], y[tr])
        preds[te] = m.predict(X[te])
    vals, counts = np.unique(y, return_counts=True)
    return (float((preds == y).mean()), float(counts.max() / counts.sum()),
            confusion_matrix(y, preds, labels=classes), classes)


def train_final(sessions, kind="rf"):
    import joblib  # noqa: F401  (fail early if missing)
    mask = pp.active_mask(np.concatenate([a for s in sessions for a in s.values()]))
    X, y, _ = build_xy(sessions, mask)
    model = build(kind).fit(X, y)
    return {"model": model, "mask": mask, "classes": [str(c) for c in model.classes_],
            "win": pp.WIN, "hop": pp.HOP, "kind": kind}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sessions", nargs="*")
    ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--model", default="rf", choices=["rf", "logreg"])
    ap.add_argument("--out", default="models/zone_model.joblib")
    args = ap.parse_args()

    if args.synthetic:
        from ml.synth import make_session
        zones = ["empty", "A", "B", "C"]
        sessions = [make_session(zones, seed=s) for s in range(4)]
    else:
        sessions = [load_session(p) for p in args.sessions]
    if len(sessions) < 2:
        sys.exit("need >= 2 sessions (record on different days/times) for honest evaluation")

    acc, base, cm, classes = evaluate(sessions, args.model)
    print(f"held-out-session accuracy {acc:.3f}  (majority baseline {base:.3f})")
    print("classes:", classes)
    print(cm)

    import joblib
    bundle = train_final(sessions, args.model)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, args.out)
    print("saved", args.out)


if __name__ == "__main__":
    main()
