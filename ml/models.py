"""Model factory. Classical first (small data, fast, interpretable)."""
from __future__ import annotations

from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def build(kind: str = "rf"):
    if kind == "rf":
        return RandomForestClassifier(n_estimators=150, min_samples_leaf=2,
                                      n_jobs=-1, random_state=0)
    if kind == "logreg":
        return make_pipeline(StandardScaler(),
                             LogisticRegression(max_iter=2000, C=0.5))
    raise ValueError(f"unknown model kind: {kind}")
