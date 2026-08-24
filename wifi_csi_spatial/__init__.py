"""Wi-Fi CSI Spatial Mapping.

Reconstruct indoor spatial information from Wi-Fi Channel State Information — a
low-cost, privacy-preserving alternative to LiDAR/cameras. Delivers the first
three roadmap phases:

    Phase 1  single obstacle detection      (one TX->RX link)
    Phase 2  multi-node sensing             (fuse all links)
    Phase 3  room boundary estimation       (reflection tomography)

Pipeline: capture -> clean (CFO/SFO + Butterworth) -> PCA -> 1D-CNN / tomography.
Capture is backend-agnostic: router today, ESP32 later, synthetic for offline.
"""

__version__ = "0.3.0"

from .config import Config, load_config  # noqa: F401
