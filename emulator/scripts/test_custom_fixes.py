"""Induced emulator test of the custom-build fixes CF-01..CF-03 (production image, set/limit.s, key/short.s, key/long.s).

    python -I emulator/scripts/test_custom_fixes.py [image [section ...]]   default image firmware/build/EEVBlog.bin
                                                       sections: keys, switch_on, peak, capture, mode (default all)

DCV / ACV / DIODE with known inputs, buzzer setting on (EEPROM 0x1E = 1).  Each case starts from a fresh meter.
CF-01  the limit test runs alone: while it is on REL (short and long), HOLD, PEAK and MIN/MAX are refused and leave
       range_manual frozen; it cannot be switched on while REL, HOLD, PEAK or MIN/MAX is on; after it the range is
       auto again and MIN/MAX works (the v0.9.4 sequence limit test on, MIN/MAX on, limit test off, MIN/MAX off left a
       manual range; REL off during the test unfroze the range).
CF-02  a Lo / HI capture while the display shows OFL is refused (nothing stored, "Lo---" stays); in range it works.
CF-03  a mode change ends the test with range_manual as the new mode sets it: DIODE 1 (v0.9.4 restored 0), ACV after a
       test started in a manual DCV range 0 (v0.9.4 restored 1).
The helpers are those of test_limit.py / test_backlight_timer.py.
"""
import os
import sys

sys.dont_write_bytecode = True                       # keep the tree free of __pycache__
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_backlight_timer as T  # noqa: E402
from test_limit import volts, goto, capture, switch, buzz_pulses  # noqa: E402

ADDR_MODE = 0x2000803C
ADDR_RANGE = 0x2000803D
ADDR_RANGE_MANUAL = 0x20008042
ADDR_MINMAX = 0x2000804E
ADDR_HOLD = 0x2000804F
ADDR_HOLD2 = 0x20008050
ADDR_REL = 0x20008058
ADDR_PEAK = 0x200080B7
ADDR_OL_LATCH = 0x20008048
EE_DIAL5 = 0x0B                                       # dial position 5 -> mode byte (11 = DIODE)


def fresh(image, patch=None):
    p = {0x1E: 1}
    p.update(patch or {})
    e = T.make(image, p)
    e.command({'dial': 2})                            # DCV
    volts(e, 1.0, 3.0)
    return e


def limits_and_on(e, a_on):
    capture(e, 28)                                    # Lo at 1.0 V
    volts(e, 1.2)
    capture(e, 29)                                    # HI at 1.2 V
    volts(e, 1.1)
    switch(e)
    goto(e, 0)
    return T.rd(e, a_on) == 1 and T.rd(e, ADDR_RANGE_MANUAL) == 1


def state(e):
    return {k: T.rd(e, a) for k, a in (('minmax', ADDR_MINMAX), ('hold', ADDR_HOLD), ('hold2', ADDR_HOLD2),
                                       ('rel', ADDR_REL), ('peak', ADDR_PEAK), ('range_manual', ADDR_RANGE_MANUAL))}


def sec_keys(image, a_on):
    print('CF-01 keys refused while the limit test is on (DCV)')
    e = fresh(image)
    T.check('limit test on, range frozen', limits_and_on(e, a_on))
    for key, longp, what in (('MINMAX', False, 'MIN/MAX short (on)'), ('MINMAX', True, 'MIN/MAX long'),
                             ('HOLD', False, 'HOLD short'), ('REL', False, 'REL short'), ('REL', True, 'REL long')):
        e.command({'key': key, 'down': True})
        e.advance(1.0 if longp else 0.15)
        e.command({'key': key, 'down': False})
        n = buzz_pulses(e, 1.0)
        s = state(e)
        T.check('%s refused: test still on, nothing switched on, range frozen' % what,
                T.rd(e, a_on) == 1 and s == dict(minmax=0, hold=0, hold2=0, rel=0, peak=0, range_manual=1),
                '%s pulses=%d' % (s, n))
    switch(e)
    goto(e, 0)
    T.check('limit test off: range_manual restored to 0 (auto)', T.rd(e, a_on) == 0 and T.rd(e, ADDR_RANGE_MANUAL) == 0)
    T.press(e, 'MINMAX', gap=0.5)
    T.check('after the test MIN/MAX goes on again (range frozen)', T.rd(e, ADDR_MINMAX) != 0 and T.rd(e, ADDR_RANGE_MANUAL) == 1)
    T.long_press(e, 'MINMAX')
    e.advance(0.5)
    T.check('MIN/MAX off: auto range again', T.rd(e, ADDR_MINMAX) == 0 and T.rd(e, ADDR_RANGE_MANUAL) == 0)



def sec_switch_on(image, a_on):
    print('CF-01 switching the test on refused while MIN/MAX, REL or HOLD is on')
    for key, addr, what in (('MINMAX', ADDR_MINMAX, 'MIN/MAX'), ('REL', ADDR_REL, 'REL'), ('HOLD', ADDR_HOLD, 'HOLD')):
        e = fresh(image)
        capture(e, 28)
        volts(e, 1.2)
        capture(e, 29)
        volts(e, 1.1)
        T.press(e, key, gap=0.6)
        on = T.rd(e, addr)
        switch(e)
        goto(e, 0)
        T.check('%s on, limit test switch-on refused' % what, on != 0 and T.rd(e, a_on) == 0, 'state=%d lt_on=%d'
                % (on, T.rd(e, a_on)))
        if key == 'MINMAX':
            T.long_press(e, 'MINMAX')
        else:
            T.press(e, key, gap=0.6)
        e.advance(0.5)
        T.check('%s off: auto range again' % what, T.rd(e, addr) == 0 and T.rd(e, ADDR_RANGE_MANUAL) == 0,
                'state=%d range_manual=%d' % (T.rd(e, addr), T.rd(e, ADDR_RANGE_MANUAL)))



def sec_peak(image, a_on):
    print('CF-01 PEAK (ACV)')
    e = fresh(image)
    T.press(e, 'MODE', gap=0.5)                      # DCV -> ACV
    e.command({'input': {'kind': 'V', 'value': 1.0, 'ac': True, 'freq': 1000}})
    e.advance(3.0)
    capture(e, 28)
    e.command({'input': {'kind': 'V', 'value': 1.2, 'ac': True, 'freq': 1000}})
    e.advance(2.0)
    capture(e, 29)
    e.command({'input': {'kind': 'V', 'value': 1.1, 'ac': True, 'freq': 1000}})
    e.advance(2.0)
    switch(e)
    goto(e, 0)
    T.check('ACV limit test on', T.rd(e, ADDR_MODE) == 2 and T.rd(e, a_on) == 1 and T.rd(e, ADDR_RANGE_MANUAL) == 1)
    T.press(e, 'PEAK', gap=0.6)
    T.check('PEAK refused while the test is on', T.rd(e, ADDR_PEAK) == 0 and T.rd(e, a_on) == 1
            and T.rd(e, ADDR_RANGE_MANUAL) == 1, str(state(e)))
    switch(e)
    goto(e, 0)
    T.press(e, 'PEAK', gap=0.6)
    peak_on = T.rd(e, ADDR_PEAK)
    switch(e)
    goto(e, 0)
    T.check('PEAK on, limit test switch-on refused', peak_on != 0 and T.rd(e, a_on) == 0, 'peak=%d' % peak_on)



def sec_capture(image, a_on):
    print('CF-02 capture refused while the display shows OFL')
    e = fresh(image)
    T.press(e, 'RANGE', gap=0.5)                     # freeze range 0 (5 V)
    volts(e, 9.0)
    ol = T.rd(e, ADDR_OL_LATCH)
    capture(e, 28)
    T.check('OFL shown (latch %d), Lo capture refused: no limit stored' % ol,
            ol == 1 and T.rd(e, a_on + 1) & 1 == 0, 'valid=%d' % T.rd(e, a_on + 1))
    goto(e, 28)
    T.check('Lo page still "Lo---"', T.sub_text(e) == 'Lo---', 'sub=%r' % T.sub_text(e))
    volts(e, 2.0)
    capture(e, 28)
    T.check('in range: the capture works', T.rd(e, a_on + 1) & 1 == 1, 'valid=%d' % T.rd(e, a_on + 1))



def sec_mode(image, a_on):
    print('CF-03 a mode change leaves the new mode\'s range lock')
    e = fresh(image, {EE_DIAL5: 11})
    T.check('limit test on (DCV, auto range before)', limits_and_on(e, a_on))
    e.command({'input': {'kind': 'open'}})
    e.command({'dial': 5})
    e.advance(3.0)
    T.check('DIODE: test ended, range_manual 1 (single range)', T.rd(e, ADDR_MODE) == 11 and T.rd(e, a_on) == 0
            and T.rd(e, ADDR_RANGE_MANUAL) == 1, 'mode=%d lt_on=%d range_manual=%d'
            % (T.rd(e, ADDR_MODE), T.rd(e, a_on), T.rd(e, ADDR_RANGE_MANUAL)))
    e = fresh(image)
    T.press(e, 'RANGE', gap=0.5)                     # manual range before the test
    T.check('limit test on (DCV, manual range before)', limits_and_on(e, a_on))
    T.press(e, 'MODE', gap=0.5)                      # DCV -> ACV
    e.command({'input': {'kind': 'V', 'value': 1.0, 'ac': True, 'freq': 1000}})
    e.advance(3.0)
    T.check('ACV: test ended, range_manual 0 (auto)', T.rd(e, ADDR_MODE) == 2 and T.rd(e, a_on) == 0
            and T.rd(e, ADDR_RANGE_MANUAL) == 0, 'mode=%d lt_on=%d range_manual=%d'
            % (T.rd(e, ADDR_MODE), T.rd(e, a_on), T.rd(e, ADDR_RANGE_MANUAL)))
    s = e.snapshot()
    T.check('no unmodelled access, no safety violation', s['unmodelled'] == 0 and not s['safety'])


SECTIONS = {'keys': sec_keys, 'switch_on': sec_switch_on, 'peak': sec_peak, 'capture': sec_capture, 'mode': sec_mode}


def run_tests(image, a_on, sections=None):
    for name in sections or SECTIONS:
        SECTIONS[name](image, a_on)


def main(argv):
    image = argv[0] if argv else os.path.join(T.ROOT, 'firmware', 'build', 'EEVBlog.bin')
    mp = os.path.join(os.path.dirname(os.path.abspath(image)), '121gw.map')
    run_tests(image, T.symbol(mp, 'lt_on'), argv[1:])
    print('RESULT', ('FAIL: ' + ', '.join(T.fails)) if T.fails else 'ALL PASS', flush=True)
    return 1 if T.fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
