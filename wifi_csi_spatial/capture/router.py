"""Router capture backend  (CURRENT hardware).

Router CSI tools (Nexmon CSI, Atheros CSI Tool, PicoScenes) each expose CSI
slightly differently but all can emit CSV. We standardise on one compact line
per link so the parser stays tiny and multi-node just means several RX ids:

    <timestamp>,<rx_id>,<rssi>,<re0>,<im0>,<re1>,<im1>, ...

Lines with the same timestamp across the configured RX ids are grouped into one
:class:`Snapshot`. Source is a saved ``.csv`` (offline) or ``udp://host:port``.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Iterator

import numpy as np

from .base import Snapshot, MultiNodeSource


def parse_line(line: str):
    """Parse ``ts,rx_id,rssi,re,im,...`` -> ``(ts, rx_id, csi)`` or ``None``."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    p = line.split(",")
    if len(p) < 5:
        return None
    ts, rx_id = float(p[0]), int(p[1])
    nums = np.array(p[3:], dtype=float)
    if nums.size % 2:
        nums = nums[:-1]
    csi = (nums[0::2] + 1j * nums[1::2]).astype(np.complex64)
    return ts, rx_id, csi


class RouterSource(MultiNodeSource):
    def __init__(self, cfg):
        self.cfg = cfg
        self.n_rx = cfg.n_rx

    def _grouped(self, lines: Iterator[str]) -> Iterator[Snapshot]:
        pending: dict[float, dict[int, np.ndarray]] = defaultdict(dict)
        for line in lines:
            parsed = parse_line(line)
            if parsed is None:
                continue
            ts, rx_id, csi = parsed
            pending[ts][rx_id] = csi
            if len(pending[ts]) >= self.n_rx:
                rows = [pending[ts][i] for i in sorted(pending[ts])]
                yield Snapshot(ts, np.stack(rows))
                del pending[ts]

    def snapshots(self) -> Iterator[Snapshot]:
        src = str(self.cfg.router_source)
        if src.startswith("udp://"):
            yield from self._grouped(self._udp_lines(src))
        else:
            path = Path(src)
            if not path.exists():
                raise FileNotFoundError(
                    f"router CSI source not found: {path}. Point "
                    f"config.router_source at a CSV log or udp://host:port."
                )
            with path.open() as fh:
                yield from self._grouped(fh)

    def _udp_lines(self, src: str) -> Iterator[str]:
        import socket
        host, port = src[len("udp://"):].split(":")
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind((host or "0.0.0.0", int(port)))
        try:
            while True:
                data, _ = sock.recvfrom(65535)
                yield data.decode("utf-8", "ignore")
        finally:
            sock.close()
