"""Leave-one-session-out validation  (roadmap step 3).

The honest way to score a CSI model. If windows from one capture leak into both
train and test, accuracy is inflated because consecutive windows are highly
correlated. LOSO holds out an *entire session* each fold, so the model must
generalise across captures — the realistic deployment condition.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import Config
from ..data.storage import Session
from ..models import ZoneClassifier
from ..pipeline import session_to_features


@dataclass
class LOSOReport:
    accuracy: float
    per_fold: dict[str, float] = field(default_factory=dict)
    labels: list[str] = field(default_factory=list)
    confusion: np.ndarray | None = None

    def __str__(self) -> str:
        lines = [f"LOSO accuracy: {self.accuracy:.3f}  "
                 f"(chance ~ {1/len(self.labels):.3f})", "per-session:"]
        for sid, acc in self.per_fold.items():
            lines.append(f"  {sid:20s} {acc:.3f}")
        return "\n".join(lines)


def leave_one_session_out(sessions: list[Session], cfg: Config) -> LOSOReport:
    if len(sessions) < 2:
        raise ValueError("need >= 2 sessions for leave-one-session-out")

    feats = [session_to_features(s, cfg) for s in sessions]
    labels = sorted({s.zone for s in sessions})
    lab_idx = {c: i for i, c in enumerate(labels)}
    conf = np.zeros((len(labels), len(labels)), dtype=int)

    per_fold, correct, total = {}, 0, 0
    for i, held in enumerate(sessions):
        X_te, y_te = feats[i]
        if len(X_te) == 0:
            continue
        X_tr = np.vstack([feats[j][0] for j in range(len(sessions)) if j != i])
        y_tr = np.concatenate([feats[j][1] for j in range(len(sessions))
                               if j != i])
        pred = ZoneClassifier().fit(X_tr, y_tr).predict(X_te)
        acc = float(np.mean(pred == y_te))
        per_fold[held.session_id] = acc
        correct += int(np.sum(pred == y_te))
        total += len(y_te)
        for t, p in zip(y_te, pred):
            conf[lab_idx[t], lab_idx[p]] += 1

    return LOSOReport(
        accuracy=correct / total if total else 0.0,
        per_fold=per_fold,
        labels=labels,
        confusion=conf,
    )
