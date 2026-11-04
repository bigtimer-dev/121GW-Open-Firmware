# Custom build C-0.96

Base: [zombu4/121GW-Open-Firmware](https://github.com/zombu4/121GW-Open-Firmware) v0.9.6 (commit a79eb20, merged), the
fast build `2_fast/EEVBlog.bin`. Personal build, not an official release. The meter shows **`C-0.96`** at power-on.

History: C-0.94 (CF-01..CF-04 on v0.9.4, commit 3e7953d) was flashed on a real 121GW on 2026-11-03: it boots, shows
`C-0.94` and measures. C-0.96 merges zombu4's v0.9.5 / v0.9.6 (IMP-22 auto-hold at 0, IMP-23 DCV window, IMP-24 4-20 mA
loop view, IMP-25 PT100 / PT1000 view, IMP-26 thermocouples N / R / S) and adds CF-05.

Every firmware change is in the production (fast) image only (`.if LOOP_V205 == 0`). The strict `1_like_v2.05` image of
this tree is byte-identical to zombu4's v0.9.6 release (SHA-256 `239ebadd…ac0c`, unchanged since v0.9.4).

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

### CF-05 DCV window on a noisy input (mdc/dcvavg.s, zombu4's IMP-23)

v0.9.5 shows DCV as a 16-sample window published every 8 samples and restarts it on a step: two samples more than a fixed
8192 AD1 codes (about 98 counts) from the running mean. On a clean source that gives twice the update rate and no
straddled value after a step, with v2.05's noise. On a noisy source (ripple aliased by the 80 samples/s converter, a
noisy supply) pairs of noise samples crossed the fixed threshold, the window restarted over and over, and most values
shown were 4-sample means. In the emulator, 1.0000 V with 60 / 120 display counts of noise per sample (fixed seed, the
same draws for every image), 20 s of Bluetooth frames:

| Noise per sample | v0.9.4 (v2.05 blocks) | v0.9.6 | C-0.96 |
|---|---|---|---|
| 60 counts: sd / peak-peak of the display | 17.2 / 76 | 27.5 / 167 | 16.3 / 83 |
| 120 counts | 34.5 / 153 | 74.3 / 382 | 32.1 / 159 |
| display updates in 20 s (60 counts) | 118 | 224 | 231 |

Fix: the threshold is max(8192 codes, 6 x the running mean absolute deviation of the samples taken into the window),
about 4.8 sigma for Gaussian noise. A clean source keeps the deviation far below the fixed threshold, so zombu4's step
behaviour is unchanged there (his `test_dcv_fast.py` gives the same results as on v0.9.6: no straddled value, the same
range-change settle time, the same noise at 8 counts); with noise the window no longer restarts on noise, and a real step
larger than about 4.8 sigma is still taken at once (1 V -> 3 V with 60 counts of noise: 3 V after 75 ms, no straddled
value). A step smaller than that is averaged as in v2.05. A range or mode change resets the estimate.
`test_custom_dcv_noise.py` checks both.

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
v0.9.6 tree rebuilds byte-identical to zombu4's v0.9.6 release (fast `b7f641f4…`, strict `239ebadd…`), as v0.9.4 did,
so the toolchain matches.

| Check | Custom C-0.96 | v0.9.6 unmodified |
|---|---|---|
| `make check-ci` (check_image, check_hy, check_gpio), both builds | PASS | PASS |
| Strict image vs zombu4's release | byte-identical | (is the release) |
| zombu4's emulator suite, 20 scripts (incl. his new `test_autohold_zero`, `test_dcv_fast`, `test_loop_percent`, `test_rtd`, `test_statistics`), about 466 checks | all pass | not rerun here (zombu4's CI) |
| `test_dcv_fast.py` (step, noise at 8 counts, range change, update rate) | all pass with `--ref` v0.9.4; with `--ref` v0.9.6 the same rate, noise and range-change time as v0.9.6 | (the reference) |
| `test_custom_dcv_noise.py` (new, CF-05: noise at 60 / 120 counts, a 1 V -> 3 V step under noise) | all pass (display sd 1.10 x sigma/4, step shown after 75 ms) | the 2 noise checks fail (1.95 x, 2.50 x) |
| `test_custom_fixes.py` (CF-01 keys / switch-on / PEAK, CF-02, CF-03, 26 checks) | all pass | 14 fail (the bugs, as on v0.9.4) |
| `test_custom_fattime.py` (`get_fattime` by direct execution, 14 calendar inputs, CF-04) | all pass | 6 fail |
| `test_custom_server.py` (emulator server / command checks, 20 cases, E-01..E-05) | all pass | n/a |
| `test_clock_frame.py` (Bluetooth set-clock frame 0xF8: checksum, echo, clock and SETUP pages, once per BT on) | all pass | not run |
| Bluetooth frames through the [Linux app](https://github.com/bigtimer-dev/121gw-linux)'s decoder: 2 and 20 frames/s, every SETUP page incl. `LP` / `Pt`, overload, remote keys, the loop / RTD views, thermocouple N | all decoded, keys as expected | not run |
| The app's own loop / RTD view (it replays the firmware's arithmetic) against the meter's LCD, 77 points | identical digits | n/a |
| Power-on splash | `C-0.96` | `F-0.96` |

Run them from the repository root with Python 3, `unicorn` and `capstone` (as the emulator), after a build
(`firmware/build/EEVBlog.bin`, map next to it). Give parallel emulator runs separate `TMPDIR`s: `test_backlight_timer.make` writes a
fixed `$TMPDIR/bl_test_eeprom.bin`, so runs that share it overwrite each other's EEPROM.

Two of zombu4's scripts still expect the SETUP page order from before the pages `rEL`, `dSP` and `CL` were added:
`test_ble_rate.py` expects item 0 after `bt` (the order since v0.9.4 is `bt` -> `rEL`, item 22) and
`test_display_level.py` item 0 after `dSP` (in DCV `dSP` -> `CL`, item 25). This fork corrects that one check in each
(as in `USER_GUIDE.md`); nothing else in them differs from zombu4's v0.9.6. In v0.9.6 zombu4 fixed `test_tc_type.py`
himself (the J and T types were never selected before), and the merge takes his version.

The emulator runs the real image instruction by instruction with modelled peripherals, but it is not the meter: analog
settling, real key bounce, the battery, the LCD glass and the real SD cards are models or absent. Run the checks of
`HARDWARE_TEST.md` and the first checks of the main `README.md` on the meter.

SHA-256 of the custom fast image C-0.96: `6f090b5d8d00b039aa2de4ad1338eede998c86d1d3d32a8ea88a0fdec3840497` (152880 bytes).
C-0.94 (tag `custom-c0.94`): `355c6ff0485987bd781f943a971da6e311018afdea8976f156ccc34cf2842580` (148228 bytes).
