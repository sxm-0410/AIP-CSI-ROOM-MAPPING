"""Room geometry + multipath physics.

The shared spatial model used by the simulator (to *make* CSI), by Phase 3 (to
*invert* CSI back into a boundary), and by the visualization. Keeping one
geometry means the reconstruction is scored against exactly the layout that
generated the signal.

Multipath model (2D):
  * one line-of-sight (direct) path  TX -> RX
  * four specular wall reflections via image sources  (encode the boundary)
  * optional single obstacle reflection  TX -> obstacle -> RX  (Phase 1/2)

CSI on subcarrier k is the coherent sum of paths:
    H_k = sum_p  g_p * exp(-j 2 pi f_k d_p / c)
with amplitude g_p ~ 1/d for the direct path and reflectivity/d for reflections.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..config import C, F0, SUBCARRIER_SPACING


def subcarrier_freqs(n: int) -> np.ndarray:
    """OFDM subcarrier absolute frequencies (Hz), centred on the carrier."""
    k = np.arange(n) - n // 2
    return F0 + k * SUBCARRIER_SPACING


@dataclass
class Room:
    w: float
    h: float
    tx: tuple[float, float]
    rx: list[tuple[float, float]]
    reflectivity: float = 0.45
    obstacle_reflectivity: float = 1.6
    shadow_depth: float = 0.7
    shadow_sigma: float = 1.0

    @classmethod
    def from_config(cls, cfg) -> "Room":
        return cls(cfg.room_w, cfg.room_h, tuple(cfg.tx),
                   [tuple(p) for p in cfg.rx], cfg.wall_reflectivity,
                   cfg.obstacle_reflectivity, cfg.shadow_depth, cfg.shadow_sigma)

    # --- image sources for the four walls -----------------------------
    def _wall_images(self, p: tuple[float, float]) -> list[tuple[float, float]]:
        x, y = p
        return [
            (-x, y),               # left  wall  x = 0
            (2 * self.w - x, y),   # right wall  x = w
            (x, -y),               # bottom wall y = 0
            (x, 2 * self.h - y),   # top   wall  y = h
        ]

    def link_paths(self, rx: tuple[float, float],
                   obstacle: tuple[float, float] | None = None
                   ) -> list[tuple[float, float]]:
        """Return ``[(path_length, gain), ...]`` for one TX->rx link."""
        tx = np.array(self.tx)
        rxa = np.array(rx)
        paths: list[tuple[float, float]] = []

        d_dir = float(np.hypot(*(tx - rxa)))
        atten = 1.0
        if obstacle is not None:
            # Radio-tomography: the obstacle attenuates the direct path by an
            # amount that falls off smoothly with its perpendicular distance to
            # the TX-RX line. Each link therefore measures a *projection* of the
            # obstacle position; links at different angles triangulate it, so
            # more nodes -> lower localization error.
            o = np.array(obstacle)
            seg = rxa - tx
            L2 = float(seg @ seg)
            t = float(np.clip((o - tx) @ seg / L2, 0.0, 1.0))
            perp = float(np.hypot(*(o - (tx + t * seg))))
            atten = 1.0 - self.shadow_depth * np.exp(-(perp / self.shadow_sigma) ** 2)
        paths.append((d_dir, atten / max(d_dir, 0.1)))        # direct (+shadow)

        for img in self._wall_images(self.tx):                # wall reflections
            d = float(np.hypot(*(np.array(img) - rxa)))
            paths.append((d, self.reflectivity / max(d, 0.1)))

        if obstacle is not None:                              # obstacle bounce
            o = np.array(obstacle)
            d = float(np.hypot(*(tx - o)) + np.hypot(*(o - rxa)))
            paths.append((d, self.obstacle_reflectivity / max(d, 0.1)))
        return paths


def synth_csi(paths: list[tuple[float, float]], freqs: np.ndarray) -> np.ndarray:
    """Coherently sum multipath into a complex CSI vector over subcarriers."""
    h = np.zeros(freqs.shape, dtype=complex)
    for d, g in paths:
        h += g * np.exp(-2j * np.pi * freqs * d / C)
    return h.astype(np.complex64)


# --- localization grid (Phase 1/2) ------------------------------------
def localization_cell(xy: tuple[float, float], cfg) -> int:
    """Room coordinate -> flat grid-cell index in [0, n_cells)."""
    x, y = xy
    col = min(cfg.grid_cols - 1, max(0, int(x / cfg.room_w * cfg.grid_cols)))
    row = min(cfg.grid_rows - 1, max(0, int(y / cfg.room_h * cfg.grid_rows)))
    return row * cfg.grid_cols + col


def cell_center(cell: int, cfg) -> tuple[float, float]:
    """Flat grid-cell index -> room coordinate of its centre (metres)."""
    row, col = divmod(int(cell), cfg.grid_cols)
    x = (col + 0.5) / cfg.grid_cols * cfg.room_w
    y = (row + 0.5) / cfg.grid_rows * cfg.room_h
    return (x, y)


# --- reconstruction grid (Phase 3) ------------------------------------
def recon_grid(cfg):
    """Cell-centre coordinate grids covering the room plus a margin.

    Returns ``(xs, ys, XX, YY)`` where XX/YY are ``(ny, nx)`` meshes.
    """
    m, res = cfg.recon_margin, cfg.recon_res
    xs = np.arange(-m, cfg.room_w + m, res)
    ys = np.arange(-m, cfg.room_h + m, res)
    XX, YY = np.meshgrid(xs, ys)
    return xs, ys, XX, YY


def rect_iou(a: tuple[float, float, float, float],
             b: tuple[float, float, float, float]) -> float:
    """IoU of two axis-aligned rectangles given as (x0, y0, x1, y1)."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    ix0, iy0 = max(ax0, bx0), max(ay0, by0)
    ix1, iy1 = min(ax1, bx1), min(ay1, by1)
    iw, ih = max(0.0, ix1 - ix0), max(0.0, iy1 - iy0)
    inter = iw * ih
    union = (ax1 - ax0) * (ay1 - ay0) + (bx1 - bx0) * (by1 - by0) - inter
    return inter / union if union > 0 else 0.0
