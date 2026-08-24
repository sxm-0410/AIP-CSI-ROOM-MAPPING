"""1D-CNN backbone  (deck: "1D-CNN operates on PCA features").

A small PyTorch 1D-CNN over the PCA feature vector (treated as a length-D,
1-channel sequence), exposed two ways sharing one backbone:

  * :class:`CNN1DClassifier`  — softmax head (obstacle present vs empty)
  * :class:`CNN1DRegressor`   — linear head (obstacle x, y in metres)

If PyTorch is unavailable both fall back to sklearn (MLPClassifier /
MLPRegressor) with the identical public API, so nothing downstream branches on
the backend.
"""
from __future__ import annotations

import numpy as np


def _torch():
    try:
        import torch
        return torch
    except Exception:
        return None


def _backbone(torch, d: int, out_dim: int):
    nn = torch.nn
    l2 = (d // 2) // 2                                 # length after two pools
    return nn.Sequential(
        nn.Unflatten(1, (1, d)),                       # (B, 1, D)
        nn.Conv1d(1, 16, 5, padding=2), nn.ReLU(), nn.MaxPool1d(2),
        nn.Conv1d(16, 32, 3, padding=1), nn.ReLU(), nn.MaxPool1d(2),
        nn.Flatten(),
        nn.Linear(32 * l2, 64), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(64, out_dim),
    )


class _BaseCNN:
    def __init__(self, epochs: int = 40, lr: float = 1e-3, seed: int = 0):
        self.epochs, self.lr, self.seed = epochs, lr, seed
        self.backend = "torch" if _torch() is not None else "sklearn"
        self._mean = self._std = self._net = self._skl = None

    def _standardize_fit(self, X):
        self._mean = X.mean(axis=0)
        self._std = X.std(axis=0) + 1e-6
        return (X - self._mean) / self._std

    def _standardize(self, X):
        return (X - self._mean) / self._std

    def _train_net(self, torch, Xs, target, out_dim, lossf, target_dtype):
        torch.manual_seed(self.seed)
        net = _backbone(torch, Xs.shape[1], out_dim)
        opt = torch.optim.Adam(net.parameters(), lr=self.lr)
        Xt = torch.tensor(Xs.astype(np.float32))
        yt = torch.tensor(target.astype(target_dtype))
        n = len(Xt)
        net.train()
        for _ in range(self.epochs):
            perm = torch.randperm(n)
            for s in range(0, n, 64):
                b = perm[s:s + 64]
                opt.zero_grad()
                loss = lossf(net(Xt[b]), yt[b])
                loss.backward()
                opt.step()
        net.eval()
        return net


class CNN1DClassifier(_BaseCNN):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.classes_ = None

    def fit(self, X, y):
        X = np.asarray(X, dtype=np.float32)
        self.classes_ = np.array(sorted(set(int(v) for v in y)))
        idx = {c: i for i, c in enumerate(self.classes_)}
        yi = np.array([idx[int(v)] for v in y], dtype=np.int64)
        Xs = self._standardize_fit(X)
        torch = _torch()
        if torch is None:
            from sklearn.neural_network import MLPClassifier
            self._skl = MLPClassifier((128, 64), max_iter=400,
                                      random_state=self.seed).fit(Xs, yi)
            return self
        self._net = self._train_net(torch, Xs, yi, len(self.classes_),
                                    torch.nn.CrossEntropyLoss(), np.int64)
        return self

    def predict_proba(self, X):
        Xs = self._standardize(np.asarray(X, dtype=np.float32))
        if self._skl is not None:
            return self._skl.predict_proba(Xs)
        torch = _torch()
        with torch.no_grad():
            return torch.softmax(self._net(torch.tensor(Xs.astype(np.float32))),
                                 dim=1).numpy()

    def predict(self, X):
        return self.classes_[self.predict_proba(X).argmax(axis=1)]


class CNN1DRegressor(_BaseCNN):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._ymean = self._ystd = None

    def fit(self, X, Y):
        X = np.asarray(X, dtype=np.float32)
        Y = np.asarray(Y, dtype=np.float32)
        self._ymean, self._ystd = Y.mean(axis=0), Y.std(axis=0) + 1e-6
        Yn = (Y - self._ymean) / self._ystd
        Xs = self._standardize_fit(X)
        torch = _torch()
        if torch is None:
            from sklearn.neural_network import MLPRegressor
            self._skl = MLPRegressor((128, 64), max_iter=600,
                                     random_state=self.seed).fit(Xs, Yn)
            return self
        self._net = self._train_net(torch, Xs, Yn, Y.shape[1],
                                    torch.nn.MSELoss(), np.float32)
        return self

    def predict(self, X):
        Xs = self._standardize(np.asarray(X, dtype=np.float32))
        if self._skl is not None:
            Yn = self._skl.predict(Xs)
        else:
            torch = _torch()
            with torch.no_grad():
                Yn = self._net(torch.tensor(Xs.astype(np.float32))).numpy()
        return Yn * self._ystd + self._ymean
