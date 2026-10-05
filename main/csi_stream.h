#pragma once
/* Start streaming CSI over the console: one line per frame
 *   CSI_DATA,<seq>,<ms>,<rssi>,<len>,[b0,b1,...]
 * (bytes are ESP-IDF int8 pairs: imag, real per subcarrier). */
void csi_stream_start(void);
/* Ping the gateway every `interval_ms` so the router keeps sending frames
 * (CSI and RSSI only refresh when a frame is received). */
void probe_start(int interval_ms);
