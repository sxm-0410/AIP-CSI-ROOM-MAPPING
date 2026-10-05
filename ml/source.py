"""Frame sources: live serial, or replay of a saved log / session CSV."""
from __future__ import annotations

from pathlib import Path
from typing import Iterator

from .csi import parse_csi_line


def serial_lines(ser) -> Iterator[str]:
    """Yield decoded lines from a pyserial port, reading in chunks.

    ``ser.readline()`` reads one byte per call; at 460800 baud with ~25 KB/s of CSI text
    it falls behind, the OS buffer overflows and rows are silently lost. Yields ``""``
    when a read times out, so callers can notice a silent port.
    """
    buf = bytearray()
    while True:
        chunk = ser.read(max(1, ser.in_waiting))
        if not chunk:
            yield ""
            continue
        buf += chunk
        while True:
            i = buf.find(b"\n")
            if i < 0:
                break
            yield bytes(buf[:i]).decode("utf-8", "ignore")
            del buf[:i + 1]
        if len(buf) > 1_000_000:          # no newline for ages: garbage, don't grow forever
            buf.clear()


def serial_frames(port: str, baud: int = 460800) -> Iterator[tuple]:
    try:
        import serial
    except ImportError as e:
        raise SystemExit("pip install -r requirements.txt") from e
    with serial.Serial(port, baud, timeout=1) as ser:
        for line in serial_lines(ser):
            f = parse_csi_line(line)
            if f is not None:
                yield f


def replay_frames(path: str | Path) -> Iterator[tuple]:
    """Raw ``CSI_DATA`` log, or a session CSV from ``ml.dataset`` (zone,ms,rssi,amps...)."""
    p = Path(path)
    with p.open() as fh:
        for i, line in enumerate(fh):
            if line.startswith("CSI_DATA"):
                f = parse_csi_line(line)
                if f is not None:
                    yield f
            else:
                r = line.strip().split(",")
                if len(r) >= 4:
                    try:
                        yield int(float(r[1])), int(float(r[2])), \
                            __import__("numpy").array(r[3:], dtype="float32")
                    except ValueError:
                        continue
