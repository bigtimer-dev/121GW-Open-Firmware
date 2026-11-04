# Custom build C-0.94

Base: [zombu4/121GW-Open-Firmware](https://github.com/zombu4/121GW-Open-Firmware) v0.9.4 (commit 3e7953d), the fast
build `2_fast/EEVBlog.bin`. Personal build, not an official release. The meter shows **`C-0.94`** at power-on.
Flashed on a real 121GW on 2026-11-03: it boots, shows `C-0.94` and measures (longer hardware checks still running).

Every firmware change is in the production (fast) image only (`.if LOOP_V205 == 0`). The strict `1_like_v2.05` image of
this tree is byte-identical to zombu4's v0.9.4 release (SHA-256 `239ebadd…ac0c`).

## Firmware fixes

### CF-01 The limit test runs alone (set/limit.s, key/short.s, key/long.s)

REL, HOLD, PEAK and MIN/MAX each freeze the range (`range_manual` 0x20008042 = 1) and save the old value in a byte of
their own; the limit test does the same. Ended in a different order than started, a feature restored a stale value.
Reproduced in the emulator on v0.9.4:

- limit test on → MIN/MAX on → limit test off → MIN/MAX off: the meter stays in a **manual range** (AUTO off) although
  nothing is on any more.
- REL on → limit test on → REL off: REL's restore **unfreezes the range during the test**; the next range change then
  ends the test without any indication. REL also turned the displayed value D into a relative value, compared against
  limits captured as absolute values.

Fix: while the limit test is on, REL (short and long), HOLD, PEAK and MIN/MAX are refused (refusal beep), like RANGE
already was; the test cannot be switched on while REL, HOLD (either stage), PEAK or MIN/MAX is on. Logging (and the
`tr-Lt` trigger) is unchanged: it starts on top of the test and restores what it saved.

### CF-02 No limit capture from an overload (set/limit.s)

A Lo / HI capture while the display shows `OFL` stored the count behind it (e.g. 9 V in the frozen 5 V range stored
90000, a value the display never shows) as a limit. It is now refused (refusal beep, nothing stored).

### CF-03 A dial turn leaves the new function's range lock (set/limit.s)

When the dial ends the test, v0.9.4 restored the `range_manual` saved when the test began, after the mode change had
already set it for the new function. DIODE (a single range, `range_manual` = 1 in v2.05) was left with 0; a test started
in a manual range left the next function in a manual range, without auto-ranging. Now a mode change ends the test without
the restore; a range change in the same function (or switching the test off) still restores it.

### CF-04 File times from a corrupt clock read (sd/diskio.s, `get_fattime`)

Only month and day were checked. A clock chip read with hour > 23, minute or second > 59 or year > 99 was packed
unchecked and carried into the neighbouring FAT date / time fields. Now any out-of-range field gives the fallback
1980-01-01 00:00:00, as an unread clock already did.

## Emulator fixes (emulator/app.py, emulator/ui/server.py, emulator/API.md)

- E-01 `{"speed": "nan"}` / `"inf"` was accepted and stopped the emulation thread (`int(NaN)` in the run loop); 0 or
  below ran nothing. Now above 0 and at most 1000, else HTTP 400 (also `--speed`).
- E-02 `/input` had no protection against other web pages: any site open in the browser could drive the emulator with a
  simple cross-origin POST. Now a request must name the server in `Host` (no DNS rebinding) and a POST with an `Origin`
  header must come from the emulator's own page (HTTP 403). curl and scripts send no `Origin` and work as documented.
- E-03 A negative `Content-Length` made the handler read until the client closed (`read(-1)`), and on `/firmware` it
  skipped the 1 MiB cap. Now HTTP 400; `/input` bodies are capped at 64 KiB.
- E-04 An upload named `.` or `..` resolved to the upload directory or its parent. Now `firmware.bin`.
- E-05 The static file check used a bare prefix test (`startswith(HERE)`), which a sibling directory such as `ui2/`
  also passed. Now `HERE + os.sep`.

## Not changed, on purpose

- The faster auto-range settle profiles (`AR_PROFILE_TP_DCV / OHM / CURRENT / AC`, `src/inc/config.inc`) stay off. Each
  waits for the hardware step test H1..H4 of `HARDWARE_TEST.md` (raw ADC codes over UART after a range change). The
  emulator does not model analog settling, so it cannot validate them; an unvalidated profile can show a not yet settled
  value after a range change. After a passed test: `make AR_PROFILE_TP_DCV=1` (etc.).
- Calibration, the data EEPROM layout and the bootloader are untouched.

## Verification

Toolchain: GNU binutils 2.46.0.20260210 (as zombu4's CI), unicorn 2.1.4 / capstone 5.0.9 for the emulator. The untouched
v0.9.4 tree rebuilds byte-identical to zombu4's release (fast `9518e15d…`, strict `239ebadd…`), so the toolchain matches.

| Check | Custom C-0.94 | v0.9.4 unmodified |
|---|---|---|
| `make check-ci` (check_image, check_hy, check_gpio), both builds | PASS | PASS |
| Strict image vs zombu4's release | byte-identical | (is the release) |
| zombu4's emulator suite, 16 scripts, 391 checks | all pass | the 3 stale scripts below fail the same way (the other 13 not rerun on it here) |
| `test_custom_fixes.py` (new, 26 checks: CF-01 keys / switch-on / PEAK, CF-02, CF-03) | all pass | 14 fail (the bugs) |
| `test_custom_fattime.py` (new, `get_fattime` by direct execution, 14 calendar inputs, CF-04) | all pass | 6 fail |
| `test_custom_server.py` (new, emulator server / command checks, 20 cases, E-01..E-05) | all pass | n/a |
| `test_clock_frame.py` (new, Bluetooth set-clock frame 0xF8: checksum, echo, clock and SETUP pages, once per BT on) | all pass | not run |
| Bluetooth frames through the [Linux app](https://github.com/bigtimer-dev/121gw-linux)'s decoder: 2 and 20 frames/s, every SETUP page, overload, remote keys | all decoded, keys as expected | not run |
| Power-on splash | `C-0.94` | `F-0.94` |
| Real 121GW (2026-11-03) | boots, `C-0.94`, measures | n/a |

Run them from the repository root with Python 3, `unicorn` and `capstone` (as the emulator), after a build
(`firmware/build/EEVBlog.bin`, map next to it). Give parallel emulator runs separate `TMPDIR`s: `test_backlight_timer.make` writes a
fixed `$TMPDIR/bl_test_eeprom.bin`, so runs that share it overwrite each other's EEPROM.

Three zombu4 scripts (`test_ble_rate.py`, `test_display_level.py`, `test_tc_type.py`) still expected the SETUP page
order from before the pages `rEL`, `dSP` and `CL` were added (e.g. `bt` -> item 0, where v0.9.4 goes `bt` -> `rEL`).
They failed the same way on the untouched v0.9.4 (byte-identical results for `test_tc_type`), and in `test_tc_type`
the wrong page meant the J and T thermocouple types were never selected. Their navigation steps now follow the order
of `USER_GUIDE.md`; nothing else in them changed, and all their checks (including every J / T reading) pass.

The emulator runs the real image instruction by instruction with modelled peripherals, but it is not the meter: analog
settling, real key bounce, the battery, the LCD glass and the real SD cards are models or absent. Run the checks of
`HARDWARE_TEST.md` and the first checks of the main `README.md` on the meter.

SHA-256 of the custom fast image: `355c6ff0485987bd781f943a971da6e311018afdea8976f156ccc34cf2842580` (148228 bytes).
