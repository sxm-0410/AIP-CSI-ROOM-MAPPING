"""Phase 3 — Room boundary estimation.

Invert the empty-room multipath back into a floor outline by ellipse
back-projection (a classic reflection-tomography idea):

  1. For each TX->RX link, form a path-length pseudo-spectrum P(d) — a matched
     filter over the CSI that peaks at the total lengths of the paths present
     (the direct path and each wall reflection).
  2. A reflector at point (x,y) contributes to a link at delay
        d(x,y) = |TX-(x,y)| + |(x,y)-RX|,
     so back-project each link's P onto the room grid at that delay and sum
     across links. Real reflectors (the walls) are reinforced where many links
     agree; the direct path is masked out first so it doesn't streak.
  3. The bright cells trace the walls; their bounding box is the estimated room,
     scored by IoU against the true rectangle.

Boundary mapping assumes a one-time CFO-calibrated empty-room scan (see
``capture.synthetic.empty_room_reference``) — standard practice, since a raw
per-frame CFO is indistinguishable from a true propagation delay.
"""
from __future__ import annotations

import numpy as np

from ..config import Config, C
from ..geometry.room import Room, subcarrier_freqs, recon_grid, rect_iou


def _delay_spectrum(H: np.ndarray, freqs: np.ndarray,
                    d_grid: np.ndarray) -> np.ndarray:
    """|matched filter|^2 of one link's CSI over candidate path lengths d."""
    steer = np.exp(2j * np.pi * np.outer(d_grid, freqs) / C)   # (D, S)
    return np.abs(steer @ H / H.size) ** 2


def estimate_reflectivity(csi_empty: np.ndarray, cfg: Config,
                          room: Room | None = None):
    """Empty-room CSI ``(R, S)`` -> back-projected reflectivity image.

    Returns ``(image (ny, nx), xs, ys)`` over the reconstruction grid.
    """
    room = room or Room.from_config(cfg)
    freqs = subcarrier_freqs(cfg.n_subcarriers)
    xs, ys, XX, YY = recon_grid(cfg)
    tx = np.array(room.tx)

    d_max = 2.0 * (cfg.room_w + cfg.room_h)
    d_grid = np.arange(0.0, d_max, 0.02)
    image = np.zeros(XX.shape, dtype=float)

    for i, rx in enumerate(room.rx):
        rxa = np.array(rx)
        d_dir = float(np.hypot(*(tx - rxa)))
        P = _delay_spectrum(csi_empty[i], freqs, d_grid)
        P[d_grid <= d_dir + 0.3] = 0.0                 # mask direct path
        if P.max() > 0:
            P = P / P.max()
        # reflection path length via each grid cell, then look up P(d)
        d_cell = np.hypot(XX - tx[0], YY - tx[1]) + np.hypot(XX - rxa[0],
                                                             YY - rxa[1])
        image += np.interp(d_cell, d_grid, P)
    return image, xs, ys


def extract_boundary(image: np.ndarray, xs: np.ndarray, ys: np.ndarray,
                     pct: float = 88.0):
    """Bounding box of the brightest reflector cells -> (x0, y0, x1, y1)."""
    thr = np.percentile(image, pct)
    mask = image >= thr
    if not mask.any():
        return (0.0, 0.0, 0.0, 0.0)
    cols = np.where(mask.any(axis=0))[0]
    rows = np.where(mask.any(axis=1))[0]
    return (float(xs[cols[0]]), float(ys[rows[0]]),
            float(xs[cols[-1]]), float(ys[rows[-1]]))


def evaluate_boundary(csi_empty: np.ndarray, cfg: Config):
    """Full Phase-3 run: reflectivity -> rectangle -> IoU vs the true room."""
    image, xs, ys = estimate_reflectivity(csi_empty, cfg)
    rect = extract_boundary(image, xs, ys)
    truth = (0.0, 0.0, cfg.room_w, cfg.room_h)
    return {
        "image": image,
        "xs": xs,
        "ys": ys,
        "rect": rect,
        "truth": truth,
        "iou": rect_iou(rect, truth),
    }
