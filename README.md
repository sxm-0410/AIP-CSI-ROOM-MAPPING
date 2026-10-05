# Wi-Fi Path Monitor (ESP32)

Detects a person or object crossing the Wi-Fi signal path between a **router** and an **ESP32**, and shows it
live on a **web dashboard** and an **OLED screen**.

Built on [ashus3868/Wi-Fi-Motion-Detector-ESP32](https://github.com/ashus3868/Wi-Fi-Motion-Detector-ESP32)
(ESP-IDF fast-scan example + a small RSSI motion task), extended with:

| Original | This project |
|---|---|
| Fixed `rssi < -50 dBm` rule, busy loop, LED only | Learns what the *empty* path looks like at boot, then alarms on signal **variation** (someone moving) or a sustained **level shift** (an object left in the path) |
| No output besides one LED | OLED status screen, serial output, **live web dashboard**, CSV logging |
| RSSI only | RSSI **and** CSI (per-subcarrier channel data, 62 subcarriers) |
| No tests | C test for the detector, Python tests for the tooling |

**What it can and cannot do (say this honestly in your presentation):** it detects that *something changed* on the
router-to-board path. It does not identify what the object is, and it cannot tell where in the room it is (one
link = one line). Room mapping is not part of the working system; see [Optional: zone map](#20-optional-zone-map-experimental).

---

## Contents
1. [What you need](#1-what-you-need)
2. [Wire the hardware](#2-wire-the-hardware)
3. [Open a terminal in the project](#3-open-a-terminal-in-the-project)
4. [ESP-IDF (the firmware toolchain)](#4-esp-idf-the-firmware-toolchain)
5. [Python environment](#5-python-environment)
6. [Find the board's serial port](#6-find-the-boards-serial-port)
7. [Enter your Wi-Fi name and password](#7-enter-your-wi-fi-name-and-password)
8. [Check the settings](#8-check-the-settings)
9. [Build](#9-build)
10. [Flash the board](#10-flash-the-board)
11. [Read the boot log: is it working?](#11-read-the-boot-log-is-it-working)
12. [Check the OLED (and optional LED)](#12-check-the-oled-and-optional-led)
13. [Quick test with the terminal monitor](#13-quick-test-with-the-terminal-monitor)
14. [Run the dashboard](#14-run-the-dashboard)
15. [Presenting: setup, demo script, backup plan](#15-presenting-setup-demo-script-backup-plan)
16. [Next time: quick start](#16-next-time-quick-start-already-flashed)
17. [Troubleshooting](#17-troubleshooting)
18. [Settings reference](#18-settings-reference)
19. [Tests](#19-tests)
20. [Optional: zone map (experimental)](#20-optional-zone-map-experimental)
21. [Project layout and how it works](#21-project-layout-and-how-it-works)

---

## 1. What you need

**Hardware**
- ESP32 dev board (classic ESP32, target `esp32`) on its expansion/breakout board.
- **USB data cable** (not a charge-only cable) from the board to your Mac.
- A Wi-Fi **router (or phone hotspot) on 2.4 GHz** with WPA2 and a known name + password. The ESP32 cannot use 5 GHz.
- **SSD1306 OLED**, 4-pin I2C (GND, VCC, SCL, SDA), 128x64 (128x32 also works, see settings).
- Optional: one LED + 220-330 ohm resistor.

**Software (on your Mac)**
- ESP-IDF **5.3.x** (this project was built and tested with **v5.3.5**).
- Python 3 (tested with 3.14) for the dashboard and tools.
- A browser (Chrome or Safari).

## 2. Wire the hardware

| Part | Connection |
|---|---|
| OLED GND | GND |
| OLED VCC | 3.3 V (check your module: most accept 3.3 V; some 5 V) |
| OLED SDA | **GPIO 21** (default) |
| OLED SCL | **GPIO 22** (default) |
| LED (optional) | GPIO 19 -> resistor -> LED anode, LED cathode -> GND |

- If your OLED is on other pins you do not have to change anything first: at boot the firmware tries 21/22, and if
  nothing answers it scans common pin pairs and logs where it found the screen (see step 12).
- Put the router and the board a few metres apart with a **clear line between them**: that line is the "path" you will
  walk through during the demo.
- Plug the board into your Mac with the USB cable.

## 3. Open a terminal in the project

Every command below is run from the project folder:

```bash
cd "/Users/sampathbageyawadi/Documents/My Projects/AIP CSI ROOM MAPPING"
```

(The quotes are required because the path contains spaces.) Use **one terminal for firmware commands** (`idf.py`,
step 4) and a **second terminal for the dashboard/Python tools** (steps 5, 13, 14).

## 4. ESP-IDF (the firmware toolchain)

**Check whether it is already installed** (it is on this Mac):

```bash
ls ~/.espressif/tools/activate_idf_v5.3.5.sh
```

- If the file is listed, you are done installing.
- If it says "No such file", install ESP-IDF 5.3.x by following Espressif's official macOS guide:
  <https://docs.espressif.com/projects/esp-idf/en/v5.3.5/esp32/get-started/index.html>, then come back.

**Activate it. You must do this in every new terminal before using `idf.py`:**

```bash
source ~/.espressif/tools/activate_idf_v5.3.5.sh
idf.py --version
```

Expected: a line ending in `ESP-IDF v5.3.5`. A warning `xtensa-esp32-elf-addr2line not found` may appear: it is
harmless (it only affects decoding crash traces).

## 5. Python environment

Use the project's virtual environment `.venv`. Create it (first time, or if it is missing/broken):

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt
```

Check it:

```bash
.venv/bin/python -c "import serial, fastapi, uvicorn, numpy; print('python ok')"
```

Expected: `python ok`.

Always call pip as `.venv/bin/python -m pip ...` (not `.venv/bin/pip`). If the project folder was ever moved, the
`.venv/bin/pip` launcher breaks with `bad interpreter` / `No such file`; the fix is to delete and recreate it:

```bash
rm -rf .venv
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

## 6. Find the board's serial port

With the board plugged in:

```bash
ls /dev/cu.*
```

Look for a name like `/dev/cu.usbserial-110` (also seen: `/dev/cu.SLAB_USBtoUART`, `/dev/cu.wchusbserial...`). That
is your **PORT**. Every command below uses `/dev/cu.usbserial-110`; **replace it with yours if different.**

- Nothing listed? Try another cable (must carry data), another USB port, and unplug/replug the board. If it still
  does not appear, install the USB-serial driver for your board's chip (Silicon Labs CP210x or WCH CH340/CH341)
  and replug.
- **Only one program can use the port at a time**: `idf.py monitor`, `tools/monitor.py`, the dashboard and flashing
  all need it. Close the others first. To see who holds it: `lsof /dev/cu.usbserial-110`.

## 7. Enter your Wi-Fi name and password

The board must join your **2.4 GHz** network (in the presentation room: your own router or phone hotspot, see step 15).
In the firmware terminal:

```bash
source ~/.espressif/tools/activate_idf_v5.3.5.sh
idf.py menuconfig
```

In the menu (arrow keys to move, **Enter** to open, **Esc** to go back):
1. Open **Example Configuration**.
2. **WiFi SSID** -> Enter -> type your network name -> Enter.
3. **WiFi Password** -> Enter -> type the password -> Enter.
4. Press **S** (save), Enter to accept the file name, then **Q** to quit.

Alternative without the menu (for simple passwords; replace the two values; avoid `|` and `&` in them):

```bash
sed -i '' 's|^CONFIG_EXAMPLE_WIFI_SSID=.*|CONFIG_EXAMPLE_WIFI_SSID="YourWiFiName"|' sdkconfig
sed -i '' 's|^CONFIG_EXAMPLE_WIFI_PASSWORD=.*|CONFIG_EXAMPLE_WIFI_PASSWORD="YourWiFiPassword"|' sdkconfig
```

**Your password is stored in `sdkconfig`.** That file is listed in `.gitignore`; never email, zip or upload it.

If there is **no `sdkconfig` file at all** (fresh copy of the project), create it first. This applies the required
settings from `sdkconfig.defaults` (460800-baud console, CSI on, 100 ms probe):

```bash
idf.py set-target esp32
```

(Do not run `set-target` on a working setup: it resets `sdkconfig`, including your Wi-Fi details.)

## 8. Check the settings

```bash
grep -E "^CONFIG_(IDF_TARGET|EXAMPLE_WIFI_SSID|ESP_CONSOLE_UART_BAUDRATE|ESPTOOLPY_MONITOR_BAUD|CSI_STREAM|ESP_WIFI_CSI_ENABLED|MOTION_PROBE_MS|MOTION_OLED)=" sdkconfig
```

Expected (SSID will be yours):

```
CONFIG_IDF_TARGET="esp32"
CONFIG_EXAMPLE_WIFI_SSID="YourWiFiName"
CONFIG_ESP_CONSOLE_UART_BAUDRATE=460800
CONFIG_ESPTOOLPY_MONITOR_BAUD=460800
CONFIG_CSI_STREAM=y
CONFIG_ESP_WIFI_CSI_ENABLED=y
CONFIG_MOTION_PROBE_MS=100
CONFIG_MOTION_OLED=y
```

If the SSID still reads `myssid`/`ssid`, redo step 7. If the baud is not `460800` or `CSI_STREAM` is missing, delete
`sdkconfig`, run `idf.py set-target esp32`, and redo step 7.

## 9. Build

```bash
idf.py build
```

The first build takes a few minutes. It ends with:

```
Project build complete. To flash, run: ...
```

If it fails, copy the first `error:` line and see [Troubleshooting](#17-troubleshooting).

## 10. Flash the board

Close any program using the port (step 6), then:

```bash
idf.py -p /dev/cu.usbserial-110 flash
```

You will see `Connecting....` then progress bars; success looks like:

```
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
Done
```

If it hangs on `Connecting........_____`, **hold the BOOT button on the board** until the percentages start, then
release. If it says the port is busy, close whatever is using it.

## 11. Read the boot log: is it working?

```bash
idf.py -p /dev/cu.usbserial-110 monitor
```

(You can combine steps 10 and 11: `idf.py -p /dev/cu.usbserial-110 flash monitor`.) To quit the monitor press
**Ctrl-]**. To restart the board while watching, press its **EN** (reset) button.

The first lines right after a reset may look like garbage: the chip's boot ROM talks at a different speed. That is
normal. After a few seconds you should see, in this order:

```
wifi:connected with <YourWiFiName>, ... channel ...
scan: got ip:192.168.x.x                         <- joined your network
oled: OLED found at 0x3C on SDA=21 SCL=22 ...    <- screen detected (see step 12)
scan: calibrating: keep the room empty           <- learning the empty path (~12 s)
MOTION,<ms>,<rssi>,<std>,<state>,<thr>,<base>,<pct>     <- ~10 lines/second
CSI_DATA,<seq>,<ms>,<rssi>,128,[...]                     <- ~10 lines/second
scan: calibrated: base=-42.4 dBm thr_std=3.52 dB thr_level=3.87 dB   <- ready
csi: probe ok=... timeout=0 restarts=0 csi_dropped=0     <- every 3 s
```

How to read a `MOTION` line: `state` is **0 = learning, 1 = path clear, 2 = object detected**; `std` is the signal
variation, `thr` the alarm limit, `base` the learned empty-path RSSI, `pct` the learning progress.

Healthy signs: `got ip` appears, `probe ok` grows by ~30 every 3 s with `timeout=0`, and `state` goes `0` then `1`.

## 12. Check the OLED (and optional LED)

On the OLED you should see, in this order:

| Screen | Meaning |
|---|---|
| `LEARNING` + `KEEP ROOM EMPTY n%` | learning the empty path (~12 s): stay out of the line between router and board |
| `IDLE` + `STD x / limit`, `BASE ... DBM` | path clear |
| `MOTION!` with a frame around the screen | object detected |

The bottom line shows the board's IP address. The optional LED **blinks while learning, is off when clear, and is on
while an object is detected**.

If the screen stays black, look at the `oled:` lines in the boot log:
- `OLED found at 0x3C on SDA=.. SCL=..` and no `I2C transaction failed` errors -> working. If it found it on pins
  other than 21/22, set those under `idf.py menuconfig` -> **Motion Detector Configuration** (OLED SDA/SCL) to skip the
  scan at boot, then rebuild and reflash.
- `no SSD1306 found; running without display` -> check wiring (VCC/GND/SDA/SCL), that it is an I2C SSD1306, and
  reseat the connections. The system still works without the screen.

## 13. Quick test with the terminal monitor

Optional but useful before the dashboard. **Close `idf.py monitor` first** (Ctrl-]).

```bash
.venv/bin/python tools/monitor.py /dev/cu.usbserial-110 --plot
```

- Status line shows `calibrating`, then `idle`, and `MOTION` when you walk through the path.
- `--plot` opens a live RSSI graph. Drop `--plot` for text only.
- It writes every sample to `logs/run_<time>.csv` (columns `ms,rssi,std,state`), flushed live.
- Stop with **Ctrl-C**.
- If it prints `no MOTION lines for 5 s`, the board is not running this firmware, the port is in use by another
  program, or the speed is wrong (it must be 460800; override with `--baud`).

## 14. Run the dashboard

Close `idf.py monitor` and `tools/monitor.py` first (the dashboard needs the port). Then:

```bash
.venv/bin/python -m ui.server --port /dev/cu.usbserial-110
```

Your browser opens **http://127.0.0.1:8000**. If it does not, open that address yourself.

- Opening the port **resets the board**, so it re-learns the empty path: the card shows **LEARNING** for ~12 s.
  **Keep the path clear until it turns green (PATH CLEAR).**
- Top right should say **live - board connected**.
- Stop the dashboard with **Ctrl-C** in its terminal.

Options: `--http-port 8001` (if port 8000 is taken), `--no-browser`, `--baud 460800`.

**What the page shows**

| Part | Meaning |
|---|---|
| Path status card | LEARNING (amber, with progress bar) / PATH CLEAR (green) / OBJECT DETECTED (red, pulsing) and how long |
| Signal (RSSI) | current signal strength and the learned empty-path baseline |
| Change vs empty path | difference from baseline in dB; negative = signal blocked |
| Variation | signal fluctuation vs the alarm limit |
| Detections / Time in alarm | counters for this browser session |
| CSI packets | channel measurements per second (about 10) |
| Two 60-second charts | signal strength and variation; **red bands = detections**; dashed lines = baseline / alarm limit |
| Heatmap | which of the 62 subcarriers are changing, last ~12 s (blank band = unused subcarriers); calm when nothing moves |
| Event log | timestamped "Object detected" / "Path clear (lasted n s)" |

**No board? Demo mode** (simulated data, with a permanent amber **DEMO MODE** banner, so it can never be mistaken for live):

```bash
.venv/bin/python -m ui.server --demo
```

## 15. Presenting: setup, demo script, backup plan

**The day before**
1. Run steps 7-14 once, at home, start to finish.
2. Rehearse the demo below, including which objects trigger it in *your* setup.
3. Decide the network you will use at the venue (below) and flash the board for it.

**Network at the venue.** The board must join a 2.4 GHz WPA2 network it can reach. The safest choice is to **bring
your own router, or use your phone's hotspot** (iPhone: Settings -> Personal Hotspot -> turn on *Maximize
Compatibility* to force 2.4 GHz). If the Wi-Fi name or password differs from what is flashed, repeat **steps 7, 9
and 10** at home before leaving (about 2 minutes). Some public/venue networks block the router ping the board uses
(client isolation): you would then see few CSI packets, though motion detection from signal strength still works.

**What to carry:** Mac + charger, board on its breakout, **data-capable USB cable**, router or hotspot phone, the
router's power adapter.

**Set up at the venue (5 minutes before)**
1. Power the router/hotspot. Place router and board 2-4 m apart, **clear line of sight between them**, both stationary.
2. Plug the board into the Mac. Open two terminals (project folder, step 3).
3. Start the dashboard (step 14). Wait for **PATH CLEAR**. Do not stand between router and board during the ~12 s of learning.

**Demo script (about 3 minutes)**
1. *"The ESP32 measures the Wi-Fi signal from the router, about ten times a second. It first learns what the empty
   path looks like."* Point at the LEARNING card, then PATH CLEAR and the flat charts.
2. *"Now I walk through the path."* Walk between router and board: the card goes red (**OBJECT DETECTED**), a red band
   appears on both charts, the heatmap lights up, the OLED shows `MOTION!`, and the event log gets a line.
3. *"I leave, and it clears after about two seconds."*
4. *"It also catches a still object left in the path."* Put a large object (or stand still in the path) and point
   at *Change vs empty path*; remove it and watch it clear. (Rehearse this: results depend on the object and position.)
5. *"This is real CSI, the same channel data used in Wi-Fi sensing research: per-subcarrier amplitude."* Show the heatmap.
6. Honest limits: it detects *that* the path changed, not what the object is or where it is; one router-to-board link
   is one line; the empty path is re-learned by pressing the board's **EN** button (keep the path clear ~12 s).

**If something breaks on stage**
- Press the board's **EN** button, wait ~12 s.
- Board lost? Ctrl-C the server, check the cable, rerun step 14.
- Last resort: `.venv/bin/python -m ui.server --demo` (simulated; say so).

## 16. Next time: quick start (already flashed)

The firmware stays on the board; you only need:

```bash
cd "/Users/sampathbageyawadi/Documents/My Projects/AIP CSI ROOM MAPPING"
.venv/bin/python -m ui.server --port /dev/cu.usbserial-110
```

Re-flash only after changing the Wi-Fi details or any setting/code: steps 3, 4, 7 (if Wi-Fi changed), 9, 10.

## 17. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `idf.py: command not found` | You skipped `source ~/.espressif/tools/activate_idf_v5.3.5.sh` in this terminal (step 4). |
| `zsh: no such file or directory ... .venv/bin/pip` / `bad interpreter` | `.venv` was created in another folder. Recreate it (step 5) and use `.venv/bin/python -m pip`. |
| A tool prints `pip install -r requirements.txt` | `pyserial` etc. missing: run `.venv/bin/python -m pip install -r requirements.txt`. |
| No `/dev/cu.usbserial*` | Charge-only cable, bad port, or missing USB driver (CP210x / CH340). Replug, try another cable. |
| `Resource busy` / port in use | Another program holds the port (`idf.py monitor`, `tools/monitor.py`, the dashboard). Close it. `lsof /dev/cu.usbserial-110` shows who. |
| Flash stuck at `Connecting....___` | Hold the **BOOT** button during connecting. Check cable and port. |
| Monitor/tool output is unreadable garbage after boot | Speed mismatch: the firmware uses **460800**. Run `idf.py ... monitor` (uses it automatically) or `tools/monitor.py ... --baud 460800`. Check step 8. |
| `got ip` never appears; repeated disconnect messages | Wrong SSID/password (redo step 7, rebuild, reflash) or a **5 GHz-only** network. Use 2.4 GHz. |
| `no MOTION lines for 5 s` / dashboard says *board not sending* | Board not running this firmware (reflash), not connected to Wi-Fi, or another program using the port. The motion task starts only after `got ip`. |
| Boot loop with `ESP_ERROR_CHECK failed` ... `csi_stream.c` | CSI support disabled in `sdkconfig`. Check `CONFIG_ESP_WIFI_CSI_ENABLED=y` (step 8) and rebuild. |
| OLED black | See step 12. Look at the `oled:` log lines; check wiring and pins; I2C SSD1306 only. |
| `I2C transaction failed` spam | Loose OLED connection. The driver disables the display after 8 failures; reseat wires and press EN. |
| Always shows OBJECT DETECTED | The empty path was not empty/steady while learning, or the board/router was moved. Press **EN**, keep the path clear ~12 s. If it still triggers on a still room, increase *level shift* or *threshold k* (step 18), rebuild, reflash. |
| Never detects you | Make sure you cross the line between router and board; lower *threshold k* / *min std margin* (step 18) for more sensitivity; check that the `Variation` and `Change vs empty path` tiles move when you walk. |
| *CSI packets* tile low or 0 | Router is ignoring the board's ping (flood protection or client isolation). Motion detection still works from signal strength. Check the `probe ok=... timeout=...` log lines; raise `Ping interval` (step 18). |
| Browser did not open | Open <http://127.0.0.1:8000> manually. |
| `Address already in use` (port 8000) | Another server is running: Ctrl-C it, or use `--http-port 8001`. |
| Charts empty / *NO SIGNAL* | The dashboard has no data yet: wait for the board (opening the port resets it), or see the rows above about the board not sending. |

## 18. Settings reference

Change with `idf.py menuconfig` -> **Motion Detector Configuration**, then **rebuild and reflash** (steps 9-10).

| Setting | Default | Effect |
|---|---|---|
| LED GPIO | 19 | pin for the optional LED |
| RSSI sample period | 100 ms | how often the signal is read |
| Sliding window | 10 samples | samples per variation window (1 s). Smaller = faster reaction |
| Calibration length | 100 windows (max 200) | how long it learns the empty path (about 12 s). Only the quietest 60% sets the limits, so a short walk-by while learning is tolerated |
| Threshold sensitivity k (x10) | 40 (= 4.0) | alarm limit = learned median + k x robust spread (never below 2x the normal level). **Lower = more sensitive** |
| Minimum std margin (dB x10) | 5 (= 0.5 dB) | minimum gap above the learned level |
| Level shift floor (dB) | 2 | lowest sustained RSSI change from baseline that can count as an object. The real limit is learned from the empty path's own jitter (shown as `thr_level` in the boot log); this is only its floor |
| Hold time | 2000 ms | alarm stays on this long after the last trigger |
| Ping the router | on | keeps signal/CSI updating (needed on an idle network) |
| Ping interval | 100 ms | = CSI rate (10/s). Faster pings can be throttled by routers |
| Stream raw CSI | on | prints `CSI_DATA` lines (needed for the heatmap) |
| OLED on / height / SDA / SCL / address / reset | on / 64 / 21 / 22 / 0x3C / -1 | screen setup (`reset 16` for Heltec-style boards) |

Fixed by `sdkconfig.defaults`: console speed 460800 baud (the CSI text needs it; 115200 is too slow, 921600 was
unreliable on this board's USB chip).

## 19. Tests

No hardware needed.

```bash
# detector logic (C)
cc -Wall -Imain test/host/test_motion.c main/motion.c -lm -o /tmp/test_motion && /tmp/test_motion
# python tooling
.venv/bin/python -m pytest -q tests
```

Expected: `motion tests passed` and `8 passed`.

## 20. Optional: zone map (experimental)

**Not needed for the presentation and not proven on real data.** With one ESP32 and one router (a single link) you
should only expect "empty vs. someone present" and maybe 2-3 coarse zones. A real room map needs more nodes.

```bash
# 1. edit config/zones.yaml to match 2-3 spots in your room (mark them on the floor)
# 2. close the dashboard/monitor, then record sessions (different times/days, same hardware positions):
.venv/bin/python tools/collect.py /dev/cu.usbserial-110 --session s1 --repeats 2
.venv/bin/python tools/collect.py /dev/cu.usbserial-110 --session s2 --repeats 2
# 3. train; it reports accuracy on a session it did not train on, next to a "guess the majority" baseline
.venv/bin/python -m ml.train data/sessions/*.csv
# 4. live zones
.venv/bin/python tools/live.py --port /dev/cu.usbserial-110 --plot
```

If held-out accuracy is not clearly above the baseline, one link cannot separate those positions. No-hardware demo of
the pipeline on synthetic data: `.venv/bin/python -m ml.train --synthetic`.

## 21. Project layout and how it works

```
main/fast_scan.c        Wi-Fi connect, 10 Hz RSSI sampling task, LED + OLED updates, prints MOTION lines
main/motion.[ch]        detector (pure C): learns empty-path baseline, variation + level-shift alarm
main/csi_stream.[ch]    CSI capture, atomic CSI_DATA output, router ping probe with auto-restart
main/oled.[ch], font5x7.h   SSD1306 driver (pin auto-scan) and font
main/Kconfig.projbuild  all settings (menuconfig)
sdkconfig.defaults      required settings re-applied on a fresh configure
test/host/test_motion.c detector test (C)
ui/server.py            dashboard server (serial reader + WebSocket + demo mode)
ui/static/index.html    dashboard page (no external dependencies, works offline)
tools/monitor.py        terminal monitor + CSV log
tools/collect.py, tools/live.py, ml/   optional zone-map pipeline
tests/test_ml.py        Python tests
```

**How detection works.** The ESP32 reads the router's signal strength (RSSI) 10 times per second and, because it pings
the router, also receives channel state information (CSI): amplitude of 62 subcarriers. For its first ~12 s it learns
the typical RSSI and the typical amount of fluctuation on the empty path. After that it raises an alarm when the
fluctuation over the last 1 s exceeds the learned limit (something moving) or the average of the last 4 samples moves
further from the baseline than the learned level limit (something left in the path), holding the alarm for 2 s after
the last trigger. The limits come from medians of the quietest 60% of the learning period, so a short walk-by while
learning does not ruin them. **Limitation:** signal strength (RSSI) is noisy (several dB of jitter even in an empty
room), so someone standing still near the board, off the direct line, may not be detected; walking through the path is.

**Status.** Developed and tested on an ESP32 (rev v3.1) with ESP-IDF 5.3.5, an SSD1306 OLED and a 2.4 GHz router.
Tested end to end: firmware builds and flashes, boot log as in step 11, dashboard with live data. The zone map is
unvalidated on real data. Credits: original motion-detector idea and base project by ashus3868.
