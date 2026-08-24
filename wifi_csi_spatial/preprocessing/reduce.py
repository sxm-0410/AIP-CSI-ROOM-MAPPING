"""Feature reduction  (deck: "Feature Reduction — PCA").

Thin PCA wrapper the phase models fit on the training features and reuse at
inference. Falls back to a numpy PCA if scikit-learn is unavailable, keeping the
same ``fit`` / ``transform`` API either way.
"""
from __future__ import annotations

import numpy as np


class PCAReducer:
    def __init__(self, n_components: int = 64):
        self.n_components = n_components
        self._impl = None
        self._mean = None
        self._comp = None

    def fit(self, X: np.ndarray) -> "PCAReducer":
        n = min(self.n_components, X.shape[0], X.shape[1])
        try:
            from sklearn.decomposition import PCA
            self._impl = PCA(n_components=n, whiten=False, random_state=0).fit(X)
        except ImportError:
            self._mean = X.mean(axis=0)
            _, _, vt = np.linalg.svd(X - self._mean, full_matrices=False)
            self._comp = vt[:n]
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        if self._impl is not None:
            return self._impl.transform(X)
        return (X - self._mean) @ self._comp.T

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).transform(X)
