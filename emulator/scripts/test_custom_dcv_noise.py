"""Induced emulator test of the custom-build fix CF-05 (src/mdc/dcvavg.s): the DCV window of IMP-23 on a noisy input.

    python -I emulator/scripts/test_custom_dcv_noise.py [image]      default firmware/build/EEVBlog.bin

The displayed DCV value is read from the Bluetooth frames (20 per second, SETUP page bt = 20), steady 1.0000 V in the
5 V range, HY3131 noise model raised to SIGMA display counts per AD1 sample (fixed seed: the same draws on every image).
  N1 noise: the standard deviation of the displayed counts over 15 s stays within 1.35 x SIGMA / 4, the standard deviation
     of a 16-sample mean (v2.05 blocks and v0.9.4: about 1.16 x).  With the fixed step threshold of v0.9.6 noise pairs
     above 98 counts restarted the window, so most values were 4-sample means: 2.0 x (60 counts) and 2.2 x (120 counts).
  N2 a real step under noise is still taken at once: 1 V -> 3 V with 60 counts of noise; every value shown after the step
     is within 0.3 % of 1 V or of 3 V (no straddled mean), and 3 V is shown within 0.2 s.
The helpers are those of test_backlight_timer.py.
"""
import os
import statistics
import sys

sys.dont_write_bytecode = True                       # keep the tree free of __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_backlight_timer as T  # noqa: E402
from app import Emulator  # noqa: E402


def meter(image, sigma):
    Emulator.hy_noise, Emulator.hy_seed = True, 7
    e = T.make(image, {0x1E: 1, 0x15: 3})            # buzzer on, Bluetooth 20 frames per second
    e.command({'dial': 2})
    e.command({'input': {'kind': 'V', 'value': 1.0, 'ac': False}})
    e.advance(3.0)
    T.long_press(e, 'PEAK')                          # Bluetooth on
    e.advance(1.0)
    e.frontend.noise_counts = sigma
    e.advance(1.5)
    return e


def frames(e, seconds):
    """(time from the start, displayed counts) of every valid frame in the next `seconds`."""
    start, t0 = len(e.ble_rx), 0.0
    out, step = [], 0.025
    marks = []
    while t0 < seconds - 1e-9:
        e.advance(step)
        t0 += step
        marks.append((len(e.ble_rx), t0))
    data = bytes(b & 0xFF for b in e.ble_rx[start:])
    i = 0
    while i + 19 <= len(data):
        f = data[i:i + 19]
        x = 0
        for b in f:
            x ^= b
        if f[0] == 0xF2 and x == 0:
            v = ((f[5] >> 6) & 3) << 16 | f[7] << 8 | f[8]
            end = start + i + 19
            t = next(tt for n, tt in marks if n >= end)
            out.append((t, -v if f[6] & 0x40 else v))
            i += 19
        else:
            i += 1
    return out


def run_tests(image):
    for sigma in (60.0, 120.0):
        e = meter(image, sigma)
        vals = [v for _, v in frames(e, 15.0)]
        sd = statistics.pstdev(vals)
        T.check('N1 sigma %d: display sd %.1f counts <= 1.35 x %.1f (%.2f x sigma/4)' % (sigma, sd, sigma / 4, sd / (sigma / 4)),
                len(vals) > 200 and sd <= 1.35 * sigma / 4, 'frames %d, p-p %d' % (len(vals), max(vals) - min(vals)))
    e = meter(image, 60.0)
    frames(e, 1.0)
    e.command({'input': {'kind': 'V', 'value': 3.0, 'ac': False}})
    after = frames(e, 1.5)
    bad = [v for _, v in after if abs(v - 10000) > 30 and abs(v - 30000) > 90]
    first = next((t for t, v in after if abs(v - 30000) <= 90), None)
    T.check('N2 step 1 V -> 3 V under noise: no straddled value', not bad, 'straddled %s' % bad[:5])
    T.check('N2 step 1 V -> 3 V under noise: 3 V shown within 0.2 s', first is not None and first <= 0.2,
            'first at %s s' % first)


def main(argv):
    image = argv[0] if argv else os.path.join(T.ROOT, 'firmware', 'build', 'EEVBlog.bin')
    print('image', image, flush=True)
    run_tests(image)
    print('RESULT', ('FAIL: ' + ', '.join(T.fails)) if T.fails else 'ALL PASS', flush=True)
    return 1 if T.fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
