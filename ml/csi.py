"""Parse CSI_DATA lines from the firmware (also tolerates esp-csi's long format)."""
from __future__ import annotations

import numpy as np


def parse_csi_line(line: str):
    """-> ``(ms, rssi, amplitude[S])`` or ``None`` for non-CSI / garbled lines.

    ESP-IDF CSI bytes are int8 pairs (imag, real) per subcarrier. Only the
    amplitude is used downstream: phase is unreliable on ESP32 hardware.
    """
    line = line.strip()
    if not line.startswith("CSI_DATA") or "[" not in line:
        return None
    head, buf = line.split("[", 1)
    f = head.rstrip(",").split(",")
    try:
        rssi = int(f[3])
        ms = int(f[2]) if len(f) > 4 else 0     # our format has ms; esp-csi's does not
        raw = np.array([int(t) for t in buf.strip(" \"]\r\n").split(",") if t.strip()],
                       dtype=float)
    except (ValueError, IndexError):
        return None
    if raw.size < 2:
        return None
    raw = raw[: raw.size - raw.size % 2]
    amp = np.hypot(raw[0::2], raw[1::2]).astype(np.float32)
    return ms, rssi, amp[2:]          # first 4 bytes are junk on ESP32 (first_word_invalid)


def parse_motion_line(line: str):
    """``MOTION,ms,rssi,std,state[,thr,base,pct]`` -> dict, or ``None`` if malformed."""
    k = line.find("MOTION,")                 # CSI/log prints can splice onto the front
    if k < 0:
        return None
    f = line[k:].strip().split(",")
    try:
        d = {"t": int(f[1]), "rssi": int(f[2]), "std": float(f[3]), "state": int(f[4])}
        d["thr"] = float(f[5]) if len(f) > 5 else None
        d["base"] = float(f[6]) if len(f) > 6 else None
        d["pct"] = int(f[7]) if len(f) > 7 else None
    except (ValueError, IndexError):
        return None
    return d
