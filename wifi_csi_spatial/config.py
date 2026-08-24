"""Project configuration for Wi-Fi CSI Spatial Mapping.

Defaults live in code so the project runs with zero setup; ``config.yaml``
(if present) overrides them. Switching the capture backend from the router to
ESP32 later is a one-line change here.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

# physical constants (5 GHz Wi-Fi, 802.11 OFDM)
C = 299_792_458.0            # speed of light (m/s)
F0 = 5.18e9                  # carrier (Hz), 802.11a/n channel 36
SUBCARRIER_SPACING = 312.5e3  # Hz


@dataclass
class Config:
    # --- capture -------------------------------------------------------
    # backend: "router" (current) | "esp32" (future) | "synthetic" (offline)
    backend: str = "synthetic"
    n_subcarriers: int = 256        # 80 MHz -> finer delay resolution
    sample_rate_hz: float = 50.0
    router_source: str = "data/raw/router_csi.csv"
    esp32_port: str = "/dev/ttyUSB0"
    esp32_baud: int = 921600

    # --- room geometry (metres) ---------------------------------------
    room_w: float = 5.0
    room_h: float = 4.0
    # one TX (corner) + several RX fanned across the far walls, so the link
    # lines cross the room at diverse angles -> better triangulation (Phase 2).
    tx: tuple[float, float] = (0.05, 0.05)
    rx: list[tuple[float, float]] = field(default_factory=lambda: [
        (4.95, 0.05),   # bottom-right
        (4.95, 2.5),    # right wall
        (4.95, 3.95),   # top-right
        (0.05, 3.95),   # top-left
    ])
    wall_reflectivity: float = 0.45
    obstacle_reflectivity: float = 1.6   # obstacle scatter strength (fingerprint)
    shadow_depth: float = 0.7            # max LOS attenuation on a link line
    shadow_sigma: float = 1.0            # corridor width of the shadow (m)   # specular reflection coefficient

    # --- localization grid (Phase 1/2) --------------------------------
    grid_rows: int = 4
    grid_cols: int = 4

    # --- boundary reconstruction grid (Phase 3) -----------------------
    recon_res: float = 0.125          # metres per cell
    recon_margin: float = 0.5         # extend recon area past the walls

    # --- cleaning ------------------------------------------------------
    hampel_window: int = 5
    hampel_sigma: float = 3.0
    butter_cutoff_hz: float = 10.0
    butter_order: int = 4

    # --- features / model ---------------------------------------------
    pca_components: int = 64
    cnn_epochs: int = 25

    # --- paths ---------------------------------------------------------
    data_dir: str = "data/datasets"
    model_dir: str = "models"

    # derived ----------------------------------------------------------
    @property
    def n_rx(self) -> int:
        return len(self.rx)

    @property
    def n_cells(self) -> int:
        return self.grid_rows * self.grid_cols

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_config(path: str | Path | None = "config.yaml") -> Config:
    cfg = Config()
    if path is None:
        return cfg
    p = Path(path)
    if not p.exists():
        return cfg
    try:
        import yaml
    except ImportError:
        return cfg
    raw = yaml.safe_load(p.read_text()) or {}
    for k, v in raw.items():
        if not hasattr(cfg, k):
            continue
        if k in ("tx",):
            v = tuple(v)
        if k == "rx":
            v = [tuple(p) for p in v]
        setattr(cfg, k, v)
    return cfg
