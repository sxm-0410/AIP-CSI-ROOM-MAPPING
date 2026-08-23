"""ESP32 capture backend  (FUTURE hardware).

Drop-in for when the project moves off the router. The ESP-IDF CSI example
prints one line per frame over USB serial:

    CSI_DATA,<seq>,<mac>,<rssi>,<rate>,...,<len>,"[i0,q0,i1,q1, ...]"

We only need the RSSI and the trailing interleaved I/Q buffer. Because it
subclasses :class:`CSISource` and yields the same :class:`CSIFrame`, nothing
downstream changes — flip ``backend: esp32`` in config and go.

Needs ``pyserial`` (listed as an optional extra); the import is deferred so the
rest of the project has zero dependency on it while we are still on the router.
"""
from __future__ import annotations

from typing import Iterator

import numpy as np

from .base import CSIFrame, CSISource


def parse_esp_line(line: str) -> CSIFrame | None:
    """Parse one ESP-IDF ``CSI_DATA,...,[i,q,i,q,...]`` line."""
    line = line.strip()
    if not line.startswith("CSI_DATA"):
        return None
    if "[" not in line or "]" not in line:
        return None
    head, buf = line.split("[", 1)
    fields = head.split(",")
    try:
        rssi = float(fields[3])
    except (IndexError, ValueError):
        rssi = float("nan")
    toks = [t for t in buf.strip(" ]\r\n").replace(" ", ",").split(",") if t]
    raw = np.array(toks, dtype=float)  # interleaved I,Q
    if raw.size % 2:
        raw = raw[:-1]
    csi = raw[0::2] + 1j * raw[1::2]
    return CSIFrame(0.0, csi.astype(np.complex64), rssi)


class ESP32Source(CSISource):
    def __init__(self, cfg):
        self.cfg = cfg
        self._ser = None

    def _open(self):
        try:
            import serial  # pyserial, optional
        except ImportError as e:  # pragma: no cover - hardware path
            raise ImportError(
                "ESP32 backend needs pyserial:  pip install pyserial"
            ) from e
        self._ser = serial.Serial(self.cfg.esp32_port, self.cfg.esp32_baud,
                                   timeout=1)

    def frames(self) -> Iterator[CSIFrame]:  # pragma: no cover - hardware path
        if self._ser is None:
            self._open()
        t0 = None
        import time
        while True:
            line = self._ser.readline().decode("utf-8", "ignore")
            frame = parse_esp_line(line)
            if frame is None:
                continue
            now = time.monotonic()
            t0 = t0 if t0 is not None else now
            frame.timestamp = now - t0  # ESP line has no wall clock
            yield frame

    def close(self) -> None:  # pragma: no cover - hardware path
        if self._ser is not None:
            self._ser.close()
            self._ser = None
