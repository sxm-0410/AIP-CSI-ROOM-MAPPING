"""Wi-Fi CSI Room Mapping.

A compact, backend-agnostic pipeline that turns raw Channel State Information
(CSI) into occupant-zone predictions:

    capture -> clean -> features -> model -> live heatmap

The capture layer is deliberately swappable. Today the signal comes from a
Wi-Fi router; the ESP32 backend is stubbed and ready to drop in later without
touching the rest of the pipeline.
"""

__version__ = "0.2.0"

from .config import Config, load_config  # noqa: F401
