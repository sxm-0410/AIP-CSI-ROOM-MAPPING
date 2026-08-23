"""Zone classifier  (roadmap step 3: "Model & validate").

XGBoost is the baseline called out on the slide. To keep the repo runnable
everywhere, the backend degrades gracefully:

    XGBoost  ->  sklearn HistGradientBoosting  ->  (both are gradient boosting)

The public API (`fit` / `predict` / `predict_proba` / `save` / `load`) is stable
regardless of backend, so swapping in the CNN/BiLSTM later means implementing
the same four methods — nothing downstream changes.
"""
from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np


def _make_estimator():
    """Prefer XGBoost; fall back to sklearn.

    Catches a broad Exception, not just ImportError: XGBoost can be installed
    yet fail to load its native library (e.g. missing OpenMP/libomp on macOS).
    Either way we want the sklearn baseline, not a crash.
    """
    try:
        from xgboost import XGBClassifier
        return XGBClassifier(
            n_estimators=300, max_depth=5, learning_rate=0.1,
            subsample=0.9, colsample_bytree=0.9,
            objective="multi:softprob", eval_metric="mlogloss",
            n_jobs=-1, tree_method="hist",
        ), "xgboost"
    except Exception:
        from sklearn.ensemble import HistGradientBoostingClassifier
        return HistGradientBoostingClassifier(
            max_iter=300, learning_rate=0.1, max_depth=6
        ), "sklearn-hgb"


class ZoneClassifier:
    def __init__(self):
        self.model, self.backend = _make_estimator()
        self.classes_: np.ndarray | None = None

    def fit(self, X: np.ndarray, y: np.ndarray) -> "ZoneClassifier":
        # encode string zone labels -> ints (both backends want that)
        self.classes_ = np.array(sorted(set(y)))
        idx = {c: i for i, c in enumerate(self.classes_)}
        yi = np.array([idx[v] for v in y])
        self.model.fit(X, yi)
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        return self.model.predict_proba(X)

    def predict(self, X: np.ndarray) -> np.ndarray:
        yi = self.model.predict(X)
        return self.classes_[np.asarray(yi, dtype=int)]

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump(self, fh)
        return path

    @staticmethod
    def load(path: str | Path) -> "ZoneClassifier":
        with Path(path).open("rb") as fh:
            return pickle.load(fh)
