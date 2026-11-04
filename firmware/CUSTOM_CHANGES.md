# Custom build C-1.03

Base: [zombu4/121GW-Open-Firmware](https://github.com/zombu4/121GW-Open-Firmware) v1.0.2 (main at commit d6651ed,
merged), the fast build `2_fast/EEVBlog.bin`. Personal build, not an official release. The meter shows **`C-1.03`** at
power-on and answers the Bluetooth version request with it.

History: C-0.94 (CF-01..CF-04 on v0.9.4, commit 3e7953d) was flashed on a real 121GW on 2026-11-03: it boots, shows
`C-0.94` and measures. C-0.96 merged zombu4's v0.9.5 / v0.9.6 (auto-hold at 0, DCV window, 4-20 mA loop view, PT100 /
PT1000 view, thermocouples N / R / S) and added CF-05. C-1.02 merges v0.9.7 .. v1.0.2 (IMP-27 battery trim, OF-30 and
LowZ bargraph fixes, IMP-28 firmware file over Bluetooth to the SD card, IMP-29 FatFs R0.16, IMP-30 version over
Bluetooth, IMP-31 every set-clock frame applied) and adds CF-06. C-1.03 adds CF-07 (the SETUP page text over Bluetooth).

Since v1.0.0 zombu4's main builds only the fast image (the like-v2.05 build moved to his branch `like-v2.05`, and the
`LOOP_V205` switches are gone from the sources); the custom changes, which were inside `.if LOOP_V205 == 0` blocks, are
now unconditional, like the rest of the fast build.

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

### CF-06 Set-clock frame range check (ble/commands.s, `fn_0800C332`)

A set-clock frame (`F8` + seven hex pairs) with a good checksum was echoed and its six values were converted to BCD and
written to the NJU6350 clock chip without any range check (v2.05 code): month 13, day 0, hour 24 or 99, minute 60 went
into the chip as they came, and from there into the SETUP pages and, through `get_fattime`, toward the SD file times
(CF-04 stops it there). v2.05 applied only the first frame per Bluetooth-on; zombu4's IMP-31 (v1.0.1) applies every frame,
so a confused or hostile Bluetooth peer can now write such values at will. Now a frame with year > 99, month not 1..12,
day not 1..31, hour > 23 or minute / second > 59 is refused like a bad checksum: not echoed, not written. Valid frames
behave as in v1.0.2 (echoed and applied every time). `test_clock_frame.py` sends four such frames; v1.0.2 writes them
to the clock.

### CF-07 SETUP page text over Bluetooth (ble/subtext.s, hooks in lcd/draw.s and ble/packet.s)

Not a defect fix but an addition for Bluetooth apps. The 19-byte status frame describes the small display only through
a v2.05 code in bytes 9..12, and only for the setup items v2.05 knew (0, 1, 2, 4, 5, 6, 7, 10, 11, 12). On every other
page it sends zeros: v2.05's own beeper (3), meter ID (8) and logging interval (9) pages, the MEM view (100) and all of
the open firmware's pages (`bL`, `bt`, `rEL`, `tc`, `dSP`, `bH`, `CL`, `Lt`, `Lo`, `HI`, `tr`, `Ch`, `n`, `Sd`, `tHI`,
`tLo`, the verdict, `LP`, `Pt`). An app cannot tell which page is shown or what it is set to.

The status frame is left exactly as it is (v2.05 apps keep working). While a SETUP page is shown, the meter now also
sends a separate 11-byte frame with what the small display shows:

    F7 item c0 c1 c2 c3 c4 flags units 00 xor
      item    the setup item (the page); 0 = back to the normal display (sent once)
      c0..c4  the five characters drawn at the small display's positions 0..4 (ASCII, as lcd_draw_glyph gets them)
      flags   bits 0..2 decimal point (digits after it, 0..4), bit 4 minus sign, bit 5 the page is being edited
      units   small display unit icons: bit 0 V, 1 A, 2 m, 3 k, 4 Hz, 5 dB, 6 Ohm
      xor     XOR of the ten bytes before it

- `lcd_draw_glyph` records each character it draws at a small-display position (5 bytes of RAM). The decimal point,
  minus sign and unit icons are read from the LCD shadow when the frame is built.
- After each status frame is built (`fn_0800C5D2`), the frame is queued with `ble_tx_queue_put`, like the command echoes
  and zombu4's version answer, and sent between status frames. It is sent when anything in it changes, else again every
  4 status frames, so an app that connects while a page is shown learns it. An unchanged normal display sends nothing.
- While a value blinks during an edit, the blank phase keeps the text of the last visible phase, so the app never
  shows a blank value.
- Nothing is sent on the page `Ld` (item 39), which owns the link for the file transfer.
- An app that does not know `0xF7` skips it, as it already skips the echoes and the `F6` version answer.

`test_custom_subtext.py` walks every page in seven dial positions and compares each frame with the emulated LCD, checks
that the status frames are unchanged, the single item-0 frame, the silence on `Ld` and on the normal display, and an
edit (edit bit, no blank phase, a REL step sent at the next frame build). The Linux app (bigtimer-dev/121gw-linux) shows
each page's name, value and an explanation from it.

zombu4's `test_ble_version.py` is adjusted: its T2 sends the remote mode key, which in DCV opens a function-option page,
so C-1.03 also sends that page's `F7` frame after the key echo. T2 now takes valid `F7` frames out before it checks
"echo of the key frame, no version frame"; any other byte still fails it.

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
- E-06 (addition) The page has a panel "Bluetooth: SETUP page text": it decodes what the meter sends (status frames
  counted, every CF-07 `F7` frame listed with the page name, text, decimal point, units and edit flag; also in `/state`
  as `ble`).
- E-07 (addition) `--host ADDRESS` serves the page also on that address of the computer (e.g. its LAN IP) for another
  device on the network. Default as before: 127.0.0.1 only. With it, requests must still name 127.0.0.1, localhost,
  [::1] or that one address (E-02 stays in force); anyone on that network can then drive the emulator.

## Not changed, on purpose

- The faster auto-range settle profiles (`AR_PROFILE_TP_DCV / OHM / CURRENT / AC`, `src/inc/config.inc`) stay off. Each
  waits for the hardware step test H1..H4 of `HARDWARE_TEST.md` (raw ADC codes over UART after a range change). The
  emulator does not model analog settling, so it cannot validate them; an unvalidated profile can show a not yet settled
  value after a range change. After a passed test: `make AR_PROFILE_TP_DCV=1` (etc.).
- Calibration, the data EEPROM layout and the bootloader are untouched.

## Verification

Toolchain: GNU binutils 2.46.0.20260210 (as zombu4's CI), unicorn 2.1.4 / capstone 5.0.9 for the emulator. The untouched
v1.0.2 tree (d6651ed) rebuilds byte-identical to zombu4's v1.0.2 release (`690a3825…9905`), so the toolchain matches.

| Check | Custom C-1.03 | v1.0.2 unmodified |
|---|---|---|
| `make check-ci` (check_image, check_hy, check_gpio) | PASS | PASS |
| Image vs zombu4's release | (custom) | byte-identical |
| The whole emulator suite, 31 scripts (zombu4's, incl. his new `test_battery_trim`, `test_ble_version`, `test_bt_upload`, `test_lowz_spike`, `test_sd_large_card`, plus this fork's) | all pass | zombu4's: his CI |
| `test_custom_fixes.py` (CF-01 keys / switch-on / PEAK, CF-02, CF-03, 26 checks) | all pass | 14 fail (the bugs are still there) |
| `test_custom_fattime.py` (`get_fattime` by direct execution, 14 calendar inputs, CF-04) | all pass | 6 fail |
| `test_custom_dcv_noise.py` (CF-05: noise at 60 / 120 counts, a 1 V -> 3 V step under noise) | all pass | the 2 noise checks fail (1.95 x, 2.50 x) |
| `test_clock_frame.py` (set-clock frame 0xF8: checksum, echo, clock and SETUP pages, every frame applied (IMP-31), CF-06 four out-of-calendar frames) | all pass | the 4 CF-06 checks fail: the clock takes the values |
| `test_custom_subtext.py` (CF-07: every SETUP page of dials 2..8 sent as on the LCD, status frames intact, item 0 once then quiet, nothing on Ld, an edit on bt) | all pass | no F7 frames at all |
| `test_custom_server.py` (emulator server / command checks, E-01..E-05) | all pass | n/a |
| Version request (IMP-30) through the [Linux app](https://github.com/bigtimer-dev/121gw-linux)'s parser | answer `C-1.03`, mode / page / HOLD / REL unchanged | `F-1.02` |
| Same request sent to C-0.96 (older firmware) | echoed, no answer, nothing changed | n/a |
| Power-on splash | `C-1.03` | `F-1.02` |
| SETUP page text (F7) decoded by the Linux app (`gw121/setup_pages.py`) on dials 2 and 5 | every page named, value as on the LCD | n/a |

Run them from the repository root with Python 3, `unicorn` and `capstone` (as the emulator), after a build
(`firmware/build/EEVBlog.bin`, map next to it). Give parallel emulator runs separate `TMPDIR`s: `test_backlight_timer.make` writes a
fixed `$TMPDIR/bl_test_eeprom.bin`, so runs that share it overwrite each other's EEPROM.

The emulator runs the real image instruction by instruction with modelled peripherals, but it is not the meter: analog
settling, real key bounce, the battery, the LCD glass and the real SD cards are models or absent. Run the checks of
`HARDWARE_TEST.md` and the first checks of the main `README.md` on the meter.

SHA-256 of the custom fast image C-1.03: `86bb99b47208d440655478337a6824ffe158a8d1be5875455884f61111e3b4df` (156080 bytes).
Earlier: C-1.02 (tag `custom-c1.02`) `f7ead63cb1547907181284a2d59a3b110eb02b591cc4386cd16bab87058f8a00` (155712 bytes),
C-0.96 (tag `custom-c0.96`) `6f090b5d8d00b039aa2de4ad1338eede998c86d1d3d32a8ea88a0fdec3840497` (152880 bytes),
C-0.94 (tag `custom-c0.94`) `355c6ff0485987bd781f943a971da6e311018afdea8976f156ccc34cf2842580` (148228 bytes).
