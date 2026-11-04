# 121GW Open Firmware: custom build C-0.96 (bigtimer-dev fork)

This is a fork of [zombu4/121GW-Open-Firmware](https://github.com/zombu4/121GW-Open-Firmware) at **v0.9.6** (fast
build, zombu4's commit `a79eb20`, merged) with five firmware fixes and five emulator fixes on top. The meter shows
**`C-0.96`** at power-on. The earlier `C-0.94` (the same fixes CF-01..CF-04 on v0.9.4, tag `custom-c0.94`) has been
running on a real 121GW since 2026-11-03.

The firmware port and the emulator are zombu4's work; this fork only adds the changes listed below. zombu4's licence
([`LICENSE`](LICENSE), unchanged) covers everything here: free to use, modify and share, never for money and never
bundled with a product. This is a personal build, not an official zombu4 or EEVblog release. Flashing is at your own
risk.

## What is different from zombu4's v0.9.6

| | Fix | Files |
|---|---|---|
| CF-01 | **The limit test runs alone.** While `Lt` is on, REL, HOLD, PEAK and MIN/MAX are refused (double beep), and `Lt` can't be switched on while one of them is on. Upstream, each of them froze the range and restored it on its own, so ending them in another order than they were started left the meter in a manual range with AUTO off, or unfroze the range during the test, so the next range change ended the test without any indication. | `firmware/src/set/limit.s`, `key/short.s`, `key/long.s` |
| CF-02 | **No `Lo` / `HI` capture from an overload.** A capture while the display showed `OFL` stored the hidden count (e.g. 9 V in the 5 V range stored 90000) as a limit. Now refused, nothing stored. | `set/limit.s` |
| CF-03 | **Turning the dial during a limit test keeps the new function's range lock.** Upstream restored the lock saved when the test started: DIODE lost its fixed range, or the next function stayed in a manual range. | `set/limit.s` |
| CF-04 | **SD log file times from a bad clock read.** Hour > 23, minute or second > 59 or year > 99 were packed unchecked into the FAT date and time. Now any bad field gives 1980-01-01 00:00, as an unread clock already did. | `sd/diskio.s` |
| CF-05 | **Steady DCV on a noisy input.** zombu4's new DCV window (v0.9.5, IMP-23) restarts on a "step" of a fixed ~98 counts. On a noisy source (ripple, a noisy supply) noise pairs crossed that threshold all the time, so most values shown were 4-sample means: in the emulator the display was 1.7 to 2.5 times as noisy as on v2.05. The threshold now follows the measured noise (6 × its mean absolute deviation, at least the fixed value): as steady as v2.05 on a noisy source, and a real step still shows at once (75 ms). On a clean source nothing changes. | `mdc/dcvavg.s` |
| E-01..E-05 | **Emulator:** speed NaN / inf / ≤ 0 refused (it stopped the emulation thread); the web UI refuses requests from other web pages (Host and Origin checks); negative or non-numeric `Content-Length` refused and `/input` capped at 64 KiB; upload names `.` / `..`; static file path check. | `emulator/app.py`, `emulator/ui/server.py` |

- CF-01..CF-04 are still present in zombu4's v0.9.6 (his later releases did not touch those files); the tests below fail
  on it.
- Every firmware change is in the production (fast) build only. The strict `1_like_v2.05` build of this tree is
  byte-identical to zombu4's v0.9.6 release.
- Details, how each bug was reproduced, and the test results: [`firmware/CUSTOM_CHANGES.md`](firmware/CUSTOM_CHANGES.md).
- All the features and how to use them, including zombu4's new ones (4–20 mA loop percent `LP`, PT100 / PT1000 `Pt`,
  thermocouples N / R / S, auto-hold at 0 Ω / 0 V): [`firmware/USER_GUIDE.md`](firmware/USER_GUIDE.md), with the
  custom changes marked.
- The faster auto-range profiles (`AR_PROFILE_TP_*`) stay off until their hardware step tests (`HARDWARE_TEST.md`
  H1..H4) are done.
- This fork publishes no release downloads; build the image as below. The *Downloads* section further down describes
  zombu4's releases.

## Build

Needs GNU binutils arm-none-eabi **2.46.0** exactly (the `Makefile` refuses other versions; zombu4's CI builds
2.46.0.20260210 from the release tarball, see `.github/workflows/firmware.yml`) and Python 3.

```sh
sh firmware/tools/build_dist.sh /tmp/dist check-ci
sha256sum /tmp/dist/2_fast/EEVBlog.bin
```

`2_fast/EEVBlog.bin` must have the SHA-256 `6f090b5d8d00b039aa2de4ad1338eede998c86d1d3d32a8ea88a0fdec3840497`
(152880 bytes). `1_like_v2.05/EEVBlog.bin` is the strict build, identical to zombu4's v0.9.6 strict image. The same
toolchain rebuilds zombu4's v0.9.6 release byte for byte.

## Flashing a 121GW

1. **Back up first**, with the firmware that is on the meter now:
   - Download EEVblog's original `EEVBlog.bin` v2.05 from EEVblog's 121GW page. It is your way back.
   - Save the calibration as `cal.bin`. This works with the original v2.05 firmware:
     1. Meter off, card in. Hold **MEM** and switch on.
     2. **Release MEM as soon as `SdCAL` shows.**
     3. Press **REL** (`SdSAv`), then **MODE** (`SAvEd`).
     4. Copy `cal.bin` from the card to your PC.

     Watch for these:
     - If MEM is still held, REL does nothing.
     - Holding MEM for about 3 s starts logging instead.
     - **PEAK** at `SdCAL` *loads* `cal.bin` from the card, overwriting the calibration. Don't press it.
2. Fresh batteries. Copy `2_fast/EEVBlog.bin` to the root of a FAT32 card, keeping the name `EEVBlog.bin`.
3. Meter off, card in. Hold **MEM + HOLD** and switch on: the display shows `-IAP-`. Press **SETUP**: `Down` shows, the
   meter writes the firmware and restarts.
4. At power-on the sub display briefly shows **`C-0.96`**, then the reading.

The bootloader is never rewritten, and the data EEPROM (calibration, serial number, settings) is not touched. The new
settings of v0.9.6 (`LP`, `Pt`) live in EEPROM bytes 0x028 and 0x029, which v2.05 never uses; an unwritten byte reads
as "off". To go back, flash the original v2.05 `EEVBlog.bin` the same way; settings and calibration stay (same EEPROM
layout). For the full checklist, see [`firmware/HARDWARE_TEST.md`](firmware/HARDWARE_TEST.md).

First checks after flashing:
- Readings in every dial position against a reference or a second meter, and the battery voltage.
- Auto power-off, the continuity beep, and a short SD log. The file date is right once the meter's clock is set.
- The limit test:
  1. On the SETUP pages `Lo` and `HI`, capture a limit: hold SETUP, press REL, hold SETUP.
  2. Switch `Lt` on.
  3. REL, HOLD, PEAK and MIN/MAX now refuse with a double beep.
- The new views, if you use them: `LP` in DC mA (4 mA = 0.00 %, 20 mA = 100.00 %), `Pt` in Ω (100.00 Ω = 0.0 °C,
  138.51 Ω = 100.0 °C).

## Bluetooth and apps

The Bluetooth frame format, the key codes and the set-clock frame are those of v2.05, so the official apps keep working.
For app developers:

- **Frame rate:** SETUP page `bt` selects 2 (default, as v2.05), 4, 10 or 20 frames per second.
- **New SETUP pages** (`bL`, `bt`, `rEL`, `dSP`, `CL`, `LP`, `Pt`, `Lt`, `Lo`, `HI`, `tr`, …) send zeros in the
  sub-display field.
- **Overload:** the bar byte is at most 25, the segments the display shows (zombu4's OF-65). v2.05 sent 45..55.
- **Display-only views:** REL in percent, the dBm reference, the 4–20 mA loop percent and the PT100 / PT1000 temperature
  change only the meter's display; Bluetooth carries the normal value (REL value, mA, Ω).
- **Thermocouples J / T / N / R / S:** the frame carries the converted temperature, as for K.
- **Remote keys during a limit test:** REL, HOLD, PEAK and MIN/MAX are refused, like the buttons.
- **Set clock:** `F8` + year − 2000, month, day, hour, minute, second and their XOR, each as two upper-case ASCII hex
  digits (15 bytes). The meter echoes the frame. It applies the first good frame after power-on or after Bluetooth is
  switched on (PEAK long), and ignores further ones until Bluetooth is switched off and on. See
  `emulator/scripts/test_clock_frame.py`.

A Linux desktop app checked against this build, including 20 frames/s, the new views and clock sync:
[bigtimer-dev/121gw-linux](https://github.com/bigtimer-dev/121gw-linux).

## Tests

Python 3 with `unicorn` and `capstone`, binutils as above:

```sh
sh firmware/tools/build_dist.sh /tmp/dist none
python3 emulator/tools/prepare_data.py --dist /tmp/dist   # once: fills emulator/data (git-ignored)
(cd firmware && make check-ci)                            # production image + map in firmware/build/
python3 -I emulator/scripts/test_custom_fixes.py          # CF-01..CF-03, 26 checks (v0.9.6: 14 fail)
python3 -I emulator/scripts/test_custom_fattime.py        # CF-04, 14 calendar inputs (v0.9.6: 6 fail)
python3 -I emulator/scripts/test_custom_dcv_noise.py      # CF-05 (v0.9.6: the two noise checks fail)
python3 -I emulator/scripts/test_custom_server.py         # E-01..E-05, 20 checks
python3 -I emulator/scripts/test_clock_frame.py           # Bluetooth set-clock frame
```

`build_dist.sh` builds the strict image last, so run `make check-ci` after it: the scripts use `firmware/build/`.
zombu4's feature test scripts in `emulator/scripts/` pass on this build too (`CUSTOM_CHANGES.md` has the list).
`test_dcv_fast.py` compares with a reference image: give it the previous release with `--ref` (its rate check T1 expects
v2.05's averaging there, about half the update rate).

---

*zombu4's original README follows, unchanged.*

# 121GW-Open-Firmware — EEVblog 121GW open firmware port and emulator

<p align="center"><img src="emulator/ui/assets/logo_anim.gif" alt="121GW running this firmware in the emulator" width="300"></p>

| Folder | Content |
|---|---|
| `firmware/` | new firmware for the 121GW (STM32L152ZD) in hand-written Thumb-2 assembly, loaded by the meter's existing bootloader at 0x08006000 |
| `emulator/` | emulator of the 121GW with a front-panel UI, used to run and test firmware without hardware |

## New features of the fast build

| Feature | Where | What it does |
|---|---|---|
| Backlight auto-off and memory | SETUP page `bL` | switches the backlight off after 30 s .. 99 min; any key or dial turn switches it on again; the on/off state is kept over a power-off |
| dBm reference | ACV, SETUP dBm page | dBm into 600, 50 or 75 ohm, or dBV |
| Bluetooth speed | SETUP page `bt` | 2, 4, 10 or 20 readings per second |
| REL in percent | SETUP page `rEL` | REL shows the deviation from the reference in % |
| Thermocouple type | TEMP, SETUP page `tc` | K, J, T, N, R or S probes |
| Display level | SETUP page `dSP` | less smoothing: small changes show about 4x sooner |
| 12-hour clock | SETUP page `CL` | time page in 12-hour form |
| Statistics | MIN/MAX, pages `n` and `Sd` | count and standard deviation of the readings |
| Continuity hold time | BEEP, SETUP page `bH` | beep latch 100 / 50 / 25 ms or off (15 ms) |
| 4–20 mA in percent | DC mA, SETUP page `LP` | a 4–20 mA or 0–20 mA loop signal shown as 0–100 % |
| PT100 / PT1000 | Ω, SETUP page `Pt` | a platinum RTD read as a temperature in °C or °F (IEC 60751) |
| Limit test | SETUP pages `Lt`, `Lo`, `HI` | PASS / HI / Lo verdict against captured limits, with beeps |
| Logging trigger | SETUP pages `tr`, `Ch` | SD records every interval, on a change, or on a limit verdict change |
| MIN/MAX times | MIN/MAX, pages `tHI`, `tLo`; SD file | when the maximum and the minimum happened, on the meter and in the closing rows of the log file |

How to set and use each one: [`firmware/USER_GUIDE.md`](firmware/USER_GUIDE.md). The `1_like_v2.05` build has none of
these and behaves like the original firmware apart from the defect fixes.

## Downloads

Every release (tag `v*`, see [Releases](../../releases)) carries:

| File | Content |
|---|---|
| `firmware-<tag>.zip` | `2_fast/EEVBlog.bin` (production build), `1_like_v2.05/EEVBlog.bin` (strict build that behaves like v2.05 apart from the defect fixes), `USER_GUIDE.md` (the new features and how to use them), `FIXES.md` (the v2.05 defects fixed), `LICENSE`, `SHA256SUMS` |
| `121GW-Open-Firmware-Emulator-<tag>-macos-arm64.dmg` | emulator for macOS on Apple chips (M1 and later) |
| `121GW-Open-Firmware-Emulator-<tag>-macos-x86_64.dmg` | emulator for macOS on Intel |
| `121GW-Open-Firmware-Emulator-<tag>-windows-x64.exe` | emulator installer for Windows 10 / 11 |
| `121GW-Open-Firmware-Emulator-<tag>-linux-amd64.deb` | emulator package for Ubuntu, Debian, Mint, Pop!_OS |
| `121GW-Open-Firmware-Emulator-<tag>-linux-x86_64.AppImage` | emulator for any other 64-bit Linux |
| `<file>.sha256` | SHA-256 of the file with that name |

No file of a release contains an original EEVblog image (bootloader, v2.05) or the calibration of any meter.

## Firmware
- Build (GNU binutils arm-none-eabi 2.46, the `Makefile` refuses other versions): `cd firmware && make` (production) or
  `make LOOP_V205=1` (strict build that behaves like v2.05 apart from the defect fixes). `make check` runs the never-brick,
  HY3131-configuration and pin-policy checks and needs the original v2.05 image in `inputs/` (not in this repository);
  `make check-ci` runs the checks that do not need it and names the ones it skips. Output: `firmware/build/EEVBlog.bin`.
  `sh firmware/tools/build_dist.sh <dir>` builds both variants into the layout of the release archive.
- CI (`.github/workflows/firmware.yml`): on every push and pull request both variants are built with GNU binutils 2.46.0
  (built from the release tarball, SHA-256 pinned; the packages of Ubuntu 24.04 and 26.04 are 2.42 and 2.45.50) and checked with `make check-ci`
  (`check_image`, `check_hy` against the committed reference data `firmware/tools/hy_reference.txt`, `check_gpio`; skipped:
  `gen_nvm_allow --check`, `gen_ram_symbols --check`, `extract_tables --verify`, which compare with the original image). On a
  tag `v*` the workflow publishes `firmware-<tag>.zip`.
- `DESIGN.md` design and deviation list, `EEPROM_MAP.md` every EEPROM byte, `ORIGINAL_FIRMWARE_ISSUES.md` the defects
  found in v2.05 (with evidence), `OPTIMIZATIONS.md`, `FEATURES.md` user-visible features (keys, display, storage; implemented in the production build: backlight
  auto-off timer with remembered on/off state, selectable dBm reference, Bluetooth frame rate 2/4/10/20 per second,
  thermocouple type K/J/T/N/R/S, REL in percent, display level, 12-hour clock, statistics, continuity hold time, limit test, logging trigger, MIN/MAX times, 4–20 mA percent, PT100/PT1000), `HARDWARE_TEST.md` checklist for the first run on a meter.
- Status: both builds match v2.05 in the emulator's 93 test scenarios and the STOP/wake scenario except documented
  deviations. Verified working on a meter (both builds). The strict build is compared frame by frame; in the production build the
  display during range changes is checked by the scenarios' assertions and final states.

### Flashing a meter from the SD card
Read `firmware/HARDWARE_TEST.md` first; it is the procedure and checklist.
1. Before flashing: dump the data EEPROM over SWD and save `cal.bin` to an SD card with v2.05 (HARDWARE_TEST.md, "Before
   flashing"). Keep both: they hold the meter's calibration, serial number and settings.
2. Unpack `firmware-<tag>.zip`. Copy one `EEVBlog.bin`, unchanged, to the root of a FAT32 SD card: `2_fast/EEVBlog.bin` or
   `1_like_v2.05/EEVBlog.bin`. The bootloader looks for exactly this file name (FAT short names ignore case).
3. Run the manual's Firmware Update procedure (page 72, summarised in HARDWARE_TEST.md, "Flashing"). The bootloader
   (0x08000000..0x08005FFF) is not changed; it writes the application from 0x08006000. The data EEPROM is not touched.
4. First boot and checks: HARDWARE_TEST.md. To return to v2.05, flash the original image the same way; settings and
   calibration stay readable (same EEPROM layout).

## Emulator
- **[How to start it, step by step with pictures](emulator/START.md).** Download, one confirmation the first time
  (the packages are not paid-signed), then it starts with a double-click; nothing else to install. On macOS and Windows
  the front panel opens in its own window (closing it stops the emulator); on Linux in the browser.
- It contains both firmware builds (choose one in the page) and loads any other `EEVBlog.bin` with **Load firmware
  file…** or by dropping the file on the window; it runs them without any original image (direct boot from the
  application's vector table) and starts with a SYNTHETIC EEPROM: made-up nominal calibration, not the calibration of any
  meter, with no serial number. Never copy it, or a `cal.bin` written by the emulator, to a meter.
- From the source tree: `sh firmware/tools/build_dist.sh /tmp/dist none && python3 emulator/tools/prepare_data.py --dist /tmp/dist`
  once (fills `emulator/data`), then `python3 emulator/app.py` and open http://127.0.0.1:8121. Needs Python 3 with
  `unicorn` and `capstone`. Own files: `--eeprom`, `--bootloader`, `--option-bytes`, `--v205-image`, `--app`, `--sdcard`;
  the original images are not included: they are read from a meter.
- `emulator/API.md`: HTTP API (`GET /state`, `POST /input`), Python API, options, what direct boot does not reproduce.
- `emulator/diff/run.py` compares two firmware images scenario by scenario (see its docstring); it needs the original v2.05
  image as the reference.
- CI (`.github/workflows/emulator.yml`) builds the packages above on a tag and attaches them to the release.

## Licence

Free to use, modify and share; selling or bundling only by zombu4 and EEVblog (David L. Jones). See `LICENSE`.
