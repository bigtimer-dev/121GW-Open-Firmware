# 121GW Open Firmware: custom build C-0.94 (bigtimer-dev fork)

This is a fork of [zombu4/121GW-Open-Firmware](https://github.com/zombu4/121GW-Open-Firmware) at **v0.9.4** (fast
build, commit `3e7953d`) with four firmware bug fixes and five emulator fixes on top. The meter shows **`C-0.94`** at
power-on. It has been running on a real 121GW since 2026-11-03.

The firmware port and the emulator are zombu4's work; this fork only adds the changes listed below. zombu4's licence
([`LICENSE`](LICENSE), unchanged) covers everything here: free to use, modify and share, never for money and never
bundled with a product. This is a personal build, not an official zombu4 or EEVblog release. Flashing is at your own
risk.

## What is different from zombu4's v0.9.4

| | Fix | Files |
|---|---|---|
| CF-01 | **The limit test runs alone.** While `Lt` is on, REL, HOLD, PEAK and MIN/MAX are refused (double beep), and `Lt` can't be switched on while one of them is on. In v0.9.4 each of them froze the range and restored it on its own, so ending them in another order than they were started left the meter in a manual range with AUTO off, or unfroze the range during the test, so the next range change ended the test without any indication. | `firmware/src/set/limit.s`, `key/short.s`, `key/long.s` |
| CF-02 | **No `Lo` / `HI` capture from an overload.** A capture while the display showed `OFL` stored the hidden count (e.g. 9 V in the 5 V range stored 90000) as a limit. Now refused, nothing stored. | `set/limit.s` |
| CF-03 | **Turning the dial during a limit test keeps the new function's range lock.** v0.9.4 restored the lock saved when the test started: DIODE lost its fixed range, or the next function stayed in a manual range. | `set/limit.s` |
| CF-04 | **SD log file times from a bad clock read.** Hour > 23, minute or second > 59 or year > 99 were packed unchecked into the FAT date and time. Now any bad field gives 1980-01-01 00:00, as an unread clock already did. | `sd/diskio.s` |
| E-01..E-05 | **Emulator:** speed NaN / inf / ≤ 0 refused (it stopped the emulation thread); the web UI refuses requests from other web pages (Host and Origin checks); negative or non-numeric `Content-Length` refused and `/input` capped at 64 KiB; upload names `.` / `..`; static file path check. | `emulator/app.py`, `emulator/ui/server.py` |

- Every firmware change is in the production (fast) build only. The strict `1_like_v2.05` build of this tree is
  byte-identical to zombu4's v0.9.4 release.
- Details, how each bug was reproduced, and the test results: [`firmware/CUSTOM_CHANGES.md`](firmware/CUSTOM_CHANGES.md).
- All the features and how to use them: [`firmware/USER_GUIDE.md`](firmware/USER_GUIDE.md) (zombu4's guide, with the
  limit-test change marked).
- **Not included:** zombu4's later releases F-0.95 and F-0.96. They add a DCV 16-sample window, auto-hold at 0 Ω / 0 V,
  4–20 mA loop percent, PT100/PT1000 and thermocouple types N/R/S, and came after this fork's base. For those, use
  zombu4's repository.
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

`2_fast/EEVBlog.bin` must have the SHA-256 `355c6ff0485987bd781f943a971da6e311018afdea8976f156ccc34cf2842580`
(148228 bytes): the image flashed on the meter, byte for byte. `1_like_v2.05/EEVBlog.bin` is the strict build, identical
to zombu4's v0.9.4 strict image.

## Flashing a 121GW

1. **Back up first**, with the firmware that is on the meter now:
   - Download EEVblog's original `EEVBlog.bin` v2.05 from EEVblog's 121GW page. It is your way back.
   - Save the calibration as `cal.bin`:
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
4. At power-on the sub display briefly shows **`C-0.94`**, then the reading.

The bootloader is never rewritten, and the data EEPROM (calibration, serial number, settings) is not touched. To go
back, flash the original v2.05 `EEVBlog.bin` the same way; settings and calibration stay (same EEPROM layout). For the
full checklist, see [`firmware/HARDWARE_TEST.md`](firmware/HARDWARE_TEST.md).

First checks after flashing:
- Readings in every dial position against a reference or a second meter, and the battery voltage.
- Auto power-off, the continuity beep, and a short SD log. The file date is right once the meter's clock is set.
- The limit test:
  1. On the SETUP pages `Lo` and `HI`, capture a limit: hold SETUP, press REL, hold SETUP.
  2. Switch `Lt` on.
  3. REL, HOLD, PEAK and MIN/MAX now refuse with a double beep.

## Bluetooth and apps

The Bluetooth frame format, the key codes and the set-clock frame are those of v2.05, so the official apps keep working.
For app developers:

- **Frame rate:** SETUP page `bt` selects 2 (default, as v2.05), 4, 10 or 20 frames per second.
- **New SETUP pages** (`bL`, `bt`, `rEL`, `dSP`, `CL`, `Lt`, `Lo`, `HI`, `tr`, …) send zeros in the sub-display field.
- **Overload:** the bar byte is at most 25, the segments the display shows (zombu4's OF-65). v2.05 sent 45..55.
- **REL in percent and the dBm reference** change only the meter's display; Bluetooth carries the normal values.
- **Remote keys during a limit test:** REL, HOLD, PEAK and MIN/MAX are refused, like the buttons.
- **Set clock:** `F8` + year − 2000, month, day, hour, minute, second and their XOR, each as two upper-case ASCII hex
  digits (15 bytes). The meter echoes the frame. It applies the first good frame after power-on or after Bluetooth is
  switched on (PEAK long), and ignores further ones until Bluetooth is switched off and on. See
  `emulator/scripts/test_clock_frame.py`.

A Linux desktop app checked against this build, including 20 frames/s and clock sync:
[bigtimer-dev/121gw-linux](https://github.com/bigtimer-dev/121gw-linux).

## Tests

Python 3 with `unicorn` and `capstone`, binutils as above:

```sh
sh firmware/tools/build_dist.sh /tmp/dist none
python3 emulator/tools/prepare_data.py --dist /tmp/dist   # once: fills emulator/data (git-ignored)
(cd firmware && make check-ci)                            # production image + map in firmware/build/
python3 -I emulator/scripts/test_custom_fixes.py          # CF-01..CF-03, 26 checks (v0.9.4: 14 fail)
python3 -I emulator/scripts/test_custom_fattime.py        # CF-04, 14 calendar inputs (v0.9.4: 6 fail)
python3 -I emulator/scripts/test_custom_server.py         # E-01..E-05, 20 checks
python3 -I emulator/scripts/test_clock_frame.py           # Bluetooth set-clock frame
```

`build_dist.sh` builds the strict image last, so run `make check-ci` after it: the scripts use `firmware/build/`. zombu4's
16 feature test scripts in `emulator/scripts/` pass too (391 checks). Three of them, `test_ble_rate.py`,
`test_display_level.py` and `test_tc_type.py`, needed their SETUP page navigation updated to the current page order;
they failed the same way on the unmodified v0.9.4.

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
| Thermocouple type | TEMP, SETUP page `tc` | K, J or T probes |
| Display level | SETUP page `dSP` | less smoothing: small changes show about 4x sooner |
| 12-hour clock | SETUP page `CL` | time page in 12-hour form |
| Statistics | MIN/MAX, pages `n` and `Sd` | count and standard deviation of the readings |
| Continuity hold time | BEEP, SETUP page `bH` | beep latch 100 / 50 / 25 ms or off (15 ms) |
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
  thermocouple type K/J/T, REL in percent, display level, 12-hour clock, statistics, continuity hold time, limit test, logging trigger, MIN/MAX times), `HARDWARE_TEST.md` checklist for the first run on a meter.
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
