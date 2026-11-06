"""Emulator test of CF-09: go straight to a SETUP page over Bluetooth (firmware/src/ble/setgoto.s).

    python -I emulator/scripts/test_setup_goto.py [image]      default firmware/build/EEVBlog.bin

Bluetooth on (long PEAK).  For the dial positions V, mV / TEMP, Ohm and Hz:
  G1 the page order is learned with the SETUP key; then every page of it (but Ld) is reached from the normal display
     with the key frame 0xC0 + item (F4 'C' x 'C' x): the frame is echoed, set_item is that page, an FA frame (CF-07)
     names it; 0xC0 goes back to the normal display (set_item 0) from every page, also from those before Ld, whose way
     round passes Ld.
  G2 0xC0 + 39 goes to the page Ld (status frames stop); there the key frames do not reach the key parser, and the
     card request 0x1C SETPAGE item(1) answers status 0 with field = the page shown, and leaves Ld (status frames
     again); 0x1C with a wrong payload (2 bytes, item 41) is refused (0x22) and stays on Ld.
  G3 refusals change nothing: a page the function does not have (tc outside TEMP), code 0xE9 (item 41).
  G4 the SETUP key still steps one page; a normal remote key (MODE) still works.
  G5 the data EEPROM is unchanged by the jumps (checked before G4's MODE key, which stores the function).
"""
import os
import sys

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import test_backlight_timer as T  # noqa: E402
import test_custom_subtext as S  # noqa: E402
import btft  # noqa: E402

ADDR_ITEM = 0x20008037
ADDR_MODE = 0x2000803C
ITEM_LD = 39


def goto_frame(item):
    hx = ('%02X' % (0xC0 + item)).encode()
    return b'\xF4' + hx + hx


def status_frames(s, seconds, e):
    n = s.f2
    for _ in range(int(seconds / 0.2)):
        e.advance(0.2)
        s.poll()
    return s.f2 - n


def learn(e):
    order = []
    for _ in range(50):
        T.press(e, 'SETUP', gap=0.3)
        item = T.rd(e, ADDR_ITEM)
        if item == 0:
            return order
        order.append(item)
    return order


def goto(e, s, item, wait=1.2):
    n0 = len(e.ble_rx)
    e.usart2.rx_feed(goto_frame(item))
    new = []
    for _ in range(int(wait / 0.2)):
        e.advance(0.2)
        new += s.poll()
    raw = bytes(e.ble_rx[n0:])
    return new, goto_frame(item) in raw


def dial_test(image, dial):
    e = T.make(image, {0x1E: 1})
    e.command({'dial': dial})
    e.advance(3.0)
    T.long_press(e, 'PEAK')
    e.advance(1.0)
    eeprom0 = bytes(e.m.eeprom)
    order = learn(e)
    print('  dial %d order: %s' % (dial, order), flush=True)
    T.check('dial %d: the SETUP key walked round (%d pages, Ld among them)' % (dial, len(order)),
            len(order) >= 15 and ITEM_LD in order)
    s = S.Stream(e)
    s.poll()
    for item in order:
        if item == ITEM_LD:
            continue
        new, echoed = goto(e, s, item)
        got = T.rd(e, ADDR_ITEM)
        named = [f for f in new if f[1] == item]
        T.check('dial %d go to %2d: echoed, shown, an FA frame names it' % (dial, item),
                echoed and got == item and bool(named), 'item %d, %d frames' % (got, len(new)))
        new, echoed = goto(e, s, 0)
        T.check('dial %d from %2d back to the normal display' % (dial, item),
                echoed and T.rd(e, ADDR_ITEM) == 0 and any(f[1] == 0 for f in new), 'item %d' % T.rd(e, ADDR_ITEM))
    return e, s, eeprom0, order


def ld_test(e, s, dial):
    goto(e, s, ITEM_LD, wait=1.0)
    T.check('dial %d go to Ld: set_item 39' % dial, T.rd(e, ADDR_ITEM) == ITEM_LD, 'item %d' % T.rd(e, ADDR_ITEM))
    T.check('dial %d on Ld: no status frames' % dial, status_frames(s, 1.0, e) == 0)
    e.usart2.rx_feed(goto_frame(0))                     # key frames do not reach the key parser on Ld
    e.advance(1.0)
    T.check('dial %d on Ld: the key frame 0xC0 does nothing' % dial, T.rd(e, ADDR_ITEM) == ITEM_LD)
    for seq, payload, why in ((1, b'\x00\x00', '2 bytes'), (2, bytes([41]), 'item 41')):
        n0 = len(e.ble_rx)
        e.usart2.rx_feed(btft.packet(0x1C, seq, payload))
        e.advance(1.0)
        ans = btft.AnswerParser().feed(bytes(e.ble_rx[n0:]))
        T.check('dial %d SETPAGE %s refused (0x22), still on Ld' % (dial, why),
                ans and ans[0].status == 0x22 and T.rd(e, ADDR_ITEM) == ITEM_LD, repr(ans))
    n0 = len(e.ble_rx)
    e.usart2.rx_feed(btft.packet(0x1C, 3, bytes([0])))
    e.advance(1.0)
    ans = btft.AnswerParser().feed(bytes(e.ble_rx[n0:]))
    T.check('dial %d SETPAGE 0 on Ld: status 0, field 0, normal display' % dial,
            ans and ans[0].status == 0 and ans[0].field == 0 and T.rd(e, ADDR_ITEM) == 0, repr(ans))
    T.check('dial %d status frames again' % dial, status_frames(s, 1.5, e) > 0)


def main():
    image = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, '..', '..', 'firmware', 'build', 'EEVBlog.bin')
    for dial in (2, 3, 5, 4):
        print('G1 dial %d' % dial, flush=True)
        e, s, eeprom0, order = dial_test(image, dial)
        print('G2 dial %d page Ld' % dial, flush=True)
        ld_test(e, s, dial)
        if dial == 2:
            print('G3 refusals', flush=True)
            goto(e, s, 23)
            T.check('tc (23) outside TEMP: refused, normal display kept', T.rd(e, ADDR_ITEM) == 0)
            T.press(e, 'SETUP', gap=0.3)
            first = T.rd(e, ADDR_ITEM)
            n0 = len(e.ble_rx)
            e.usart2.rx_feed(b'\xF4E9E9')
            e.advance(1.0)
            T.check('code 0xE9 (item 41): echoed, nothing changes', T.rd(e, ADDR_ITEM) == first
                    and b'\xF4E9E9' in bytes(e.ble_rx[n0:]))
            print('G4 the keys still work', flush=True)
            T.press(e, 'SETUP', gap=0.3)
            T.check('SETUP key: the next page (%d)' % order[1], T.rd(e, ADDR_ITEM) == order[1],
                    'item %d' % T.rd(e, ADDR_ITEM))
            goto(e, s, 0)
            T.check('dial 2 data EEPROM unchanged by the page jumps', bytes(e.m.eeprom) == eeprom0)
            mode0 = T.rd(e, ADDR_MODE)                  # MODE stores the function (rotary memory, v2.05): last
            e.usart2.rx_feed(b'\xF4' + b'0505')
            e.advance(1.0)
            T.check('remote MODE key still changes the mode', T.rd(e, ADDR_MODE) != mode0)
        else:
            T.check('dial %d data EEPROM unchanged' % dial, bytes(e.m.eeprom) == eeprom0)
    print('RESULT', ('FAIL: ' + ', '.join(T.fails)) if T.fails else 'ALL PASS', flush=True)
    sys.stdout.flush()
    os._exit(1 if T.fails else 0)


if __name__ == '__main__':
    main()
