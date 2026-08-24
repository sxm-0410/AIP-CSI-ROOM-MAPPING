"""Shared obstacle localizer used by Phase 1 (one link) and Phase 2 (all links).

Pipeline: clean CSI -> per-link amplitude/phase features -> PCA -> 1D-CNN, with
two heads sharing the backbone:

  * a presence classifier (obstacle vs empty room), and
  * an (x, y) regressor that triangulates the per-link shadow "tripwires".

Same code both phases; the only difference is which ``links`` feed in — exactly
the single-node vs multi-node distinction from the roadmap. More links means
more crossing tripwires, so the regressor localizes better.
"""
from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from ..config import Config
from ..dataset import SpatialDataset
from ..features import batch_features, snapshot_features
from ..preprocessing import PCAReducer
from ..models import CNN1DClassifier, CNN1DRegressor


@dataclass
class LocEval:
    presence_acc: float      # empty vs occupied
    loc_error_m: float       # mean localization error on occupied samples
    n_nodes: int


class Localizer:
    def __init__(self, cfg: Config, links: list[int]):
        self.cfg = cfg
        self.links = links
        self.pca = PCAReducer(cfg.pca_components)
        self.presence = CNN1DClassifier(epochs=cfg.cnn_epochs)
        self.regressor = CNN1DRegressor(epochs=cfg.cnn_epochs)

    # --- train --------------------------------------------------------
    def fit(self, ds: SpatialDataset) -> "Localizer":
        Z = self.pca.fit_transform(batch_features(ds.csi, self.cfg, self.links))
        occupied = (ds.label != self.cfg.n_cells).astype(int)
        self.presence.fit(Z, occupied)
        m = occupied.astype(bool)
        self.regressor.fit(Z[m], ds.xy[m])
        return self

    # --- inference ----------------------------------------------------
    def _features(self, csi_rs: np.ndarray) -> np.ndarray:
        x = snapshot_features(csi_rs, self.cfg, self.links)[None, :]
        return self.pca.transform(x)

    def predict(self, csi_rs: np.ndarray) -> dict:
        z = self._features(csi_rs)
        present = bool(self.presence.predict(z)[0] == 1)
        conf = float(self.presence.predict_proba(z)[0].max())
        xy = tuple(float(v) for v in self.regressor.predict(z)[0])
        return {"present": present, "xy": xy if present else None,
                "confidence": conf}

    def heatmap(self, csi_rs: np.ndarray) -> list[float]:
        """Soft per-cell occupancy for the demo grid (gaussian at the estimate)."""
        from ..geometry.room import cell_center
        est = self.predict(csi_rs)
        vals = []
        for c in range(self.cfg.n_cells):
            if not est["present"]:
                vals.append(0.0)
                continue
            cx, cy = cell_center(c, self.cfg)
            d = np.hypot(cx - est["xy"][0], cy - est["xy"][1])
            vals.append(float(np.exp(-(d / 0.9) ** 2)))
        return vals

    # --- evaluation ---------------------------------------------------
    def evaluate(self, ds: SpatialDataset) -> LocEval:
        Z = self.pca.transform(batch_features(ds.csi, self.cfg, self.links))
        occupied = ds.label != self.cfg.n_cells
        pres_pred = self.presence.predict(Z).astype(int)
        presence_acc = float(np.mean(pres_pred == occupied.astype(int)))
        if occupied.any():
            xy_pred = self.regressor.predict(Z[occupied])
            err = float(np.mean(np.hypot(*(xy_pred - ds.xy[occupied]).T)))
        else:
            err = float("nan")
        return LocEval(presence_acc, err, len(self.links))

    # --- persistence --------------------------------------------------
    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as fh:
            pickle.dump(self, fh)
        return path

    @staticmethod
    def load(path: str | Path) -> "Localizer":
        with Path(path).open("rb") as fh:
            return pickle.load(fh)
