"""Router capture backend  (CURRENT hardware).

Router CSI tools (Nexmon CSI, the Atheros CSI Tool, PicoScenes, ...) all expose
CSI a little differently, but every one of them can be coaxed into emitting
CSV lines. We standardise on one compact line format so the parser stays tiny
and the upstream tool choice stays flexible:

    <timestamp>,<rssi>,<re0>,<im0>,<re1>,<im1>, ... ,<reN>,<imN>

The source can be a saved ``.csv`` file (offline) or a live ``udp://host:port``
stream the router logger pushes to (online). Point ``router_source`` at either.
"""
from __future__ import annotations

import socket
from pathlib import Path
from typing import Iterator

import numpy as np

from .base import CSIFrame, CSISource


def parse_csv_line(line: str) -> CSIFrame | None:
    """Parse one ``ts,rssi,re,im,re,im,...`` line into a frame."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    parts = line.split(",")
    if len(parts) < 4:
        return None
    ts = float(parts[0])
    rssi = float(parts[1]) if parts[1] not in ("", "nan") else float("nan")
    nums = np.array(parts[2:], dtype=float)
    if nums.size % 2:  # need pairs of (real, imag)
        nums = nums[:-1]
    csi = nums[0::2] + 1j * nums[1::2]
    return CSIFrame(ts, csi.astype(np.complex64), rssi)


class RouterSource(CSISource):
    def __init__(self, cfg):
        self.cfg = cfg
        self.source = cfg.router_source
        self._sock: socket.socket | None = None

    def _udp_frames(self, host: str, port: int) -> Iterator[CSIFrame]:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind((host, port))
        while True:
            data, _ = self._sock.recvfrom(65535)
            frame = parse_csv_line(data.decode("utf-8", "ignore"))
            if frame is not None:
                yield frame

    def _file_frames(self, path: Path) -> Iterator[CSIFrame]:
        with path.open() as fh:
            for line in fh:
                frame = parse_csv_line(line)
                if frame is not None:
                    yield frame

    def frames(self) -> Iterator[CSIFrame]:
        src = str(self.source)
        if src.startswith("udp://"):
            host, port = src[len("udp://"):].split(":")
            yield from self._udp_frames(host or "0.0.0.0", int(port))
        else:
            path = Path(src)
            if not path.exists():
                raise FileNotFoundError(
                    f"router CSI source not found: {path}. Point config."
                    f"router_source at your CSV log or a udp://host:port stream."
                )
            yield from self._file_frames(path)

    def close(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None
