"""Project configuration.

Defaults live in code so the project runs with zero setup. A `config.yaml`
(if present) overrides them, so switching from the router backend to ESP32
later is a one-line change and no code edits.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any


@dataclass
class Zone:
    """An occupant zone and where it sits on the room heatmap grid."""
    name: str
    row: int
    col: int


@dataclass
class Config:
    # --- capture -------------------------------------------------------
    # backend: "router" (current) | "esp32" (future) | "synthetic" (offline)
    backend: str = "synthetic"
    n_subcarriers: int = 64
    sample_rate_hz: float = 100.0
    # router backend
    router_source: str = "data/raw/router_csi.csv"   # file / UDP host:port
    # esp32 backend
    esp32_port: str = "/dev/ttyUSB0"
    esp32_baud: int = 921600

    # --- cleaning ------------------------------------------------------
    hampel_window: int = 5
    hampel_sigma: float = 3.0
    butter_cutoff_hz: float = 10.0
    butter_order: int = 4

    # --- features / windowing -----------------------------------------
    window: int = 128          # frames per feature window
    hop: int = 64              # stride between windows

    # --- layout --------------------------------------------------------
    grid_rows: int = 2
    grid_cols: int = 2
    zones: list[Zone] = field(default_factory=lambda: [
        Zone("empty", 0, 0),
        Zone("desk", 0, 1),
        Zone("door", 1, 0),
        Zone("window", 1, 1),
    ])

    # --- paths ---------------------------------------------------------
    data_dir: str = "data/sessions"
    model_path: str = "models/zone_clf.pkl"

    @property
    def zone_names(self) -> list[str]:
        return [z.name for z in self.zones]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_config(path: str | Path | None = "config.yaml") -> Config:
    """Load config from YAML if it exists, else return baked-in defaults."""
    cfg = Config()
    if path is None:
        return cfg
    p = Path(path)
    if not p.exists():
        return cfg
    try:
        import yaml  # optional dependency
    except ImportError:
        return cfg
    raw = yaml.safe_load(p.read_text()) or {}
    zones = raw.pop("zones", None)
    for k, v in raw.items():
        if hasattr(cfg, k):
            setattr(cfg, k, v)
    if zones:
        cfg.zones = [Zone(**z) for z in zones]
    return cfg
