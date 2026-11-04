"""Bluetooth set-clock frame (as apps send it): 0xF8 + 7 ASCII hex pairs, upper case: year - 2000, month, day, hour,
minute, second and the XOR of those six.  Same frame and rules as v2.05 (firmware/src/ble/commands.s fn_0800C332):
a bad checksum is ignored; a good frame is echoed and applied to the clock; only the first good frame after power-on
or after Bluetooth is switched on (PEAK long) is applied, later ones are echoed and ignored until Bluetooth is
switched off and on.  The SETUP year / date / time pages must show the new time.

    python -I emulator/scripts/test_clock_frame.py [image]   default firmware/build/EEVBlog.bin
"""
import os
import sys

sys.dont_write_bytecode = True                       # keep the tree free of __pycache__
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.normpath(os.path.join(HERE, '..', '..'))
IMAGE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(REPO, 'firmware', 'build', 'EEVBlog.bin')
sys.path.insert(0, HERE)
import test_backlight_timer as T            # noqa: E402

RTC = 0x200080D7                                    # calendar copy: year - 2000, month, day, hour, minute, second
ITEM = 0x20008037
fails = []


def check(name, ok, detail=''):
    print('  %s %-56s %s' % ('PASS' if ok else 'FAIL', name, detail), flush=True)
    if not ok:
        fails.append(name)


def frame(y, mo, d, h, mi, s, bad=False):
    v = [y - 2000, mo, d, h, mi, s]
    x = 0
    for b in v:
        x ^= b
    if bad:
        x ^= 0x55
    return bytes([0xF8]) + ''.join('%02X' % b for b in v + [x]).encode('ascii')


def rtc(e):
    return tuple(T.rd(e, RTC + i) for i in range(6))


def page(e, item):
    e.m.uc.mem_write(ITEM, bytes([item]))
    e.m.uc.mem_write(0x20008062, bytes([1]))
    e.advance(0.6)
    return T.sub_text(e)


e = T.make(IMAGE, {0x1E: 1})
e.command({'dial': 2})
e.advance(3.0)
T.long_press(e, 'PEAK')                             # BT transfer on
e.advance(1.0)
print('  clock before:', rtc(e), flush=True)
f = frame(2031, 7, 9, 13, 45, 20, bad=True)
e.usart2.rx_feed(f)
e.advance(2.0)
check('bad checksum: clock unchanged', rtc(e)[:3] != (31, 7, 9), str(rtc(e)))
f = frame(2031, 7, 9, 13, 45, 20)
print('  frame:', f, flush=True)
start = len(e.ble_rx)
e.usart2.rx_feed(f)
e.advance(2.0)
echo = bytes(b & 0xFF for b in e.ble_rx[start:])
check('meter echoes the frame', f in echo)
r = rtc(e)
check('clock set to 2031-07-09 13:45:2x', r[:5] == (31, 7, 9, 13, 45) and 20 <= r[5] <= 23, str(r))
check('SETUP year page shows 2031', page(e, 5).strip() == '2031', repr(page(e, 5)))
check('SETUP date page shows 07-09', page(e, 6) == '07-09', repr(page(e, 6)))
t = page(e, 7)
check('SETUP time page shows 13-45 (separator blinks)', t.replace(' ', '-') == '13-45', repr(t))
page(e, 0)
e.usart2.rx_feed(frame(2032, 1, 1, 0, 0, 0))
e.advance(2.0)
check('a second frame in the same BT session is ignored (v2.05 rule)', rtc(e)[:3] == (31, 7, 9), str(rtc(e)))
T.long_press(e, 'PEAK')                             # BT off
e.advance(0.5)
T.long_press(e, 'PEAK')                             # BT on again
e.advance(1.0)
e.usart2.rx_feed(frame(2032, 1, 1, 0, 0, 0))
e.advance(2.0)
check('after BT off/on a new frame is applied', rtc(e)[:3] == (32, 1, 1), str(rtc(e)))
print('RESULT', 'ALL PASS' if not fails else 'FAIL: ' + ', '.join(fails), flush=True)
sys.stdout.flush()
os._exit(1 if fails else 0)
