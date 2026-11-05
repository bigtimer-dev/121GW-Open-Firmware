"""Emulator test of CF-07: the SETUP page text frame FA (firmware/src/ble/subtext.s, firmware/CUSTOM_CHANGES.md).

    python -I emulator/scripts/test_custom_subtext.py [image]      default firmware/build/EEVBlog.bin

  S1 every page: in each dial position SETUP is pressed until the item is 0 again; on every page (item != 0, not Ld) the
     last FA frame names that item and its five characters and decimal point show what the LCD's sub display shows
     (compared as seven-segment patterns of the firmware's font: the LCD decoder reads 'b' as 'B' and 'O' as '0').
  S2 the status frames: every F2 frame keeps its 19 bytes and checksum while FA frames are sent.
  S3 leaving the pages: one FA with item 0, then no FA for 3 s.
  S4 page Ld: no FA frames (the page owns the link for the file transfer).
  S5 an edit (page bt): the frames carry the edit bit, the text never shows the blank blink phase, and a REL step is sent
     with the new value at the next frame build (within 1 s).
"""
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test_backlight_timer as T  # noqa: E402

ADDR_ITEM = 0x20008037
ITEM_LD, ITEM_BT = 39, 21
FONT_D = [0xBB, 0x11, 0xA7, 0x97, 0x1D, 0x9E, 0xBE, 0x1B, 0xBF, 0x9F]
FONT_U = [0x3F, 0xBC, 0xAA, 0xB5, 0xAE, 0x2E, 0x9F, 0x3D, 0x11, 0xB1, 0x2D, 0xA8, 0xBF, 0x3B, 0xBB, 0x2F,
          0x1F, 0x2A, 0x9E, 0xAC, 0xB9, 0xB9, 0xB9, 0x1C, 0x9D, 0x86]
FONT_L = [0x3F, 0xBC, 0xA4, 0xB5, 0xAE, 0x2E, 0x9F, 0x3C, 0x10, 0xB1, 0x2D, 0xA8, 0xBF, 0x34, 0xB4, 0x2F,
          0x1F, 0x24, 0x9E, 0xAC, 0xB0, 0xB0, 0xB0, 0x1C, 0x9D, 0x86]


def seg(c):
    o = ord(c)
    if 48 <= o <= 57:
        return FONT_D[o - 48]
    if 65 <= o <= 90:
        return FONT_U[o - 65]
    if 97 <= o <= 122:
        return FONT_L[o - 97]
    return {' ': 0, '-': 4, '=': 0x82, '\xff': 0xBF}.get(c, -1)


class Stream:
    """Splits what the meter sent into status frames (F2, 19 bytes) and text frames (FA, 11 bytes)."""

    def __init__(self, e):
        self.e, self.seen, self.buf = e, len(e.ble_rx), b''
        self.f2, self.f7, self.bad_f2 = 0, [], 0

    def poll(self):
        self.buf += bytes(b & 0xFF for b in self.e.ble_rx[self.seen:])
        self.seen = len(self.e.ble_rx)
        i, out = 0, []
        while i < len(self.buf):
            b = self.buf[i]
            if b == 0xF2 and i + 19 <= len(self.buf):
                x = 0
                for v in self.buf[i:i + 19]:
                    x ^= v
                if x == 0:
                    self.f2 += 1
                    i += 19
                    continue
            if b == 0xFA and i + 11 <= len(self.buf):
                x = 0
                for v in self.buf[i:i + 11]:
                    x ^= v
                if x == 0:
                    out.append(self.buf[i:i + 11])
                    i += 11
                    continue
            if b in (0xF2, 0xFA) and i + 19 > len(self.buf):
                break                                   # wait for the rest
            i += 1
        self.buf = self.buf[i:]
        self.f7 += out
        return out


def lcd_sub(e):
    """(segment patterns of the five characters, decimal digits) of the LCD's sub display."""
    t = T.sub_text(e)
    dp = 0
    if '.' in t:
        k = t.index('.')
        dp = len(t[k + 1:].replace('.', ''))
        t = t.replace('.', '')
    t = t.rjust(5)[-5:]
    return [seg(c) for c in t], dp, T.sub_text(e)


def frame_sub(f):
    chars = ''.join(chr(c) for c in f[2:7])
    return [seg(c) for c in chars], f[7] & 7, chars


def walk(image, dial, mA=False):
    e = T.make(image, {0x1E: 1})
    if mA:
        e.command({'jack': 'mA', 'plugged': True})
    e.command({'dial': dial})
    e.advance(3.0)
    T.long_press(e, 'PEAK')                         # Bluetooth on
    e.advance(1.0)
    s = Stream(e)
    s.poll()
    pages = []
    for _ in range(45):
        T.press(e, 'SETUP', gap=0.4)
        item = T.rd(e, ADDR_ITEM)
        new = []
        for _ in range(6):                          # 1.2 s: the change is sent at once, the repeat every 4 frames
            e.advance(0.2)
            new += s.poll()
        if item == 0:
            break
        if item == ITEM_LD:
            T.check('dial %d page Ld: no FA frame' % dial, not new, '%d frames' % len(new))
            continue
        last = [f for f in new if f[1] == item]
        if not last:
            T.check('dial %d item %d: an FA frame' % (dial, item), False, 'none of %d frames' % len(new))
            continue
        f = last[-1]
        want, dp, shown = lcd_sub(e)
        got, fdp, chars = frame_sub(f)
        if item == 7:                               # the time page blinks its hour-minute separator ('-' / ' ') each second
            want[2] = got[2] = 0
        T.check('dial %d item %2d %-7r frame %-7r dp %d' % (dial, item, shown, chars, fdp),
                want == got and dp == fdp, 'lcd %r dp %d' % (shown, dp))
        pages.append(item)
    # leaving: one FA with item 0, then quiet
    zero = [f for f in s.f7 if f[1] == 0]
    T.check('dial %d back to item 0: one FA with item 0' % dial, len(zero) == 1, '%d' % len(zero))
    n7 = len(s.f7)
    for _ in range(15):
        e.advance(0.2)
        s.poll()
    T.check('dial %d no FA for 3 s on the normal display' % dial, len(s.f7) == n7, '%d more' % (len(s.f7) - n7))
    T.check('dial %d status frames kept coming (%d)' % (dial, s.f2), s.f2 > 20)
    return e, s, pages


def edit_test(image):
    e = T.make(image, {0x1E: 1})
    e.command({'dial': 2})
    e.advance(3.0)
    T.long_press(e, 'PEAK')
    e.advance(1.0)
    e.m.uc.mem_write(ADDR_ITEM, bytes([20]))        # bL, then SETUP: bt
    T.press(e, 'SETUP', gap=0.6)
    T.check('on page bt', T.rd(e, ADDR_ITEM) == ITEM_BT, 'item %d' % T.rd(e, ADDR_ITEM))
    s = Stream(e)
    e.advance(3.0)                                  # the page change went out before the stream began: wait for a repeat
    s.poll()
    before = s.f7[-1] if s.f7 else None
    T.long_press(e, 'SETUP')                        # edit: the value blinks
    s.f7.clear()
    for _ in range(15):
        e.advance(0.2)
        s.poll()
    frames = [f for f in s.f7 if f[1] == ITEM_BT]
    T.check('edit: frames carry the edit bit', frames and all(f[7] & 0x20 for f in frames), '%d frames' % len(frames))
    T.check('edit: never the blank phase', frames and all(bytes(f[5:7]).strip() for f in frames),
            repr([bytes(f[2:7]) for f in frames]))
    s.f7.clear()
    T.press(e, 'REL', gap=0.1)                      # one step up
    e.advance(1.0)                                  # the next frame build (2 per second at bt 2)
    s.poll()
    after = [f for f in s.f7 if f[1] == ITEM_BT]
    T.check('edit: the REL step is sent with the new value within 1 s',
            after and before is not None and bytes(after[-1][2:7]) != bytes(before[2:7]),
            '%r -> %r' % (before and bytes(before[2:7]), after and bytes(after[-1][2:7])))
    T.press(e, 'SETUP')                             # end the edit without saving


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'firmware', 'build', 'EEVBlog.bin')
    seen = set()
    for dial, mA in ((2, False), (3, False), (4, False), (5, False), (6, False), (7, False), (8, True)):
        print('S1..S4 dial %d' % dial, flush=True)
        _, _, pages = walk(image, dial, mA)
        seen.update(pages)
    print('pages seen:', sorted(seen))
    T.check('pages of the open firmware seen (bL, bt, rEL, dSP, CL)', {20, 21, 22, 24, 25} <= seen, str(sorted(seen)))
    print('S5 edit', flush=True)
    edit_test(image)
    print('RESULT', ('FAIL: ' + ', '.join(T.fails)) if T.fails else 'ALL PASS', flush=True)
    sys.stdout.flush()
    os._exit(1 if T.fails else 0)


if __name__ == '__main__':
    main()
