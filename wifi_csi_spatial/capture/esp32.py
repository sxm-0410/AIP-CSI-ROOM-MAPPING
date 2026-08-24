"""ESP32 capture backend  (FUTURE hardware).

Per the first-review architecture (ESP32-S3 TX/RX nodes). The ESP-IDF CSI
example prints one line per frame over USB serial:

    CSI_DATA,<seq>,<mac>,<rssi>,<rate>,...,[i0,q0,i1,q1, ...]

We tag each serial stream with the RX node id it belongs to and group frames
into multi-node :class:`Snapshot` objects. Because it yields the same Snapshot,
flipping ``backend: esp32`` in config is the only change needed — no pipeline
edits. Needs ``pyserial`` (optional extra); import is deferred.
"""
from __future__ import annotations

import time
from typing import Iterator

import numpy as np

from .base import Snapshot, MultiNodeSource


def parse_esp_line(line: str):
    """Parse one ESP-IDF ``CSI_DATA,...,[i,q,i,q,...]`` line -> csi or None."""
    line = line.strip()
    if not line.startswith("CSI_DATA") or "[" not in line:
        return None
    head, buf = line.split("[", 1)
    fields = head.split(",")
    toks = [t for t in buf.strip(" ]\r\n").replace(" ", ",").split(",") if t]
    raw = np.array(toks, dtype=float)
    if raw.size % 2:
        raw = raw[:-1]
    return (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)


class ESP32Source(MultiNodeSource):
    def __init__(self, cfg):
        self.cfg = cfg
        self._sers: list = []

    def _open(self):  # pragma: no cover - hardware path
        try:
            import serial
        except ImportError as e:
            raise ImportError("ESP32 backend needs pyserial: "
                              "pip install pyserial") from e
        # one serial handle per RX node (ports comma-separated in esp32_port)
        ports = str(self.cfg.esp32_port).split(",")
        self._sers = [serial.Serial(p.strip(), self.cfg.esp32_baud, timeout=1)
                      for p in ports]

    def snapshots(self) -> Iterator[Snapshot]:  # pragma: no cover - hardware
        if not self._sers:
            self._open()
        t0 = time.monotonic()
        while True:
            rows = []
            for ser in self._sers:
                csi = None
                while csi is None:
                    csi = parse_esp_line(ser.readline().decode("utf-8", "ignore"))
                rows.append(csi)
            yield Snapshot(time.monotonic() - t0, np.stack(rows))

    def close(self) -> None:  # pragma: no cover - hardware path
        for ser in self._sers:
            ser.close()
        self._sers = []
