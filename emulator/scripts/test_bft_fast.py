"""Induced emulator test of the fast card reads of the Bluetooth link (production image, CF-08, firmware/src/ble/bftfast.s).

    python -I emulator/scripts/test_bft_fast.py [image]            default firmware/build/EEVBlog.bin

Card and page as test_bft_files.py (Bluetooth on, SETUP page Ld).
  F1 STREAM with the page's defaults (pace 13, gap 2): 1100 .. 1300 bytes/s; 8192 bytes of BIG.BIN staged by READ, streamed in pieces of 64 bytes: every piece arrives once, in
     order, with a good CRC, and they reassemble to the file's bytes; the 0x82 answer comes first and names the count.
  F2 LINK pace 12: answered with the BRR; the stream then sends at most 12 bytes per 10 ms tick (at most 132 in any
     100 ms window, which can touch 11 ticks), 1000 .. 1300 bytes/s, and is complete.
  F3 LINK stop bits 2 and trim +3: USART2 CR2 STOP = 2 and BRR = start BRR + 3 once the answer has left, the answer itself
     was sent with the old format; trim 0 and 1 stop bit restore the start values; arguments out of range are refused
     (0x22) and change nothing.
  F7 gap 1, 2, 4 (idle frame after every gap bytes) with 2 stop bits: streams complete and equal; gap 33 refused.
  F4 a request during a stream ends it: its answer arrives and no piece follows it.
  F5 STREAM arguments: size 0 and 233, nothing staged, first beyond the end are refused (0x22); count cut at the end
     (last piece shorter).
  F6 the data EEPROM and the card are unchanged.
"""
import os
import struct
import sys
import zlib

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import test_backlight_timer as T  # noqa: E402
import test_bt_upload as U  # noqa: E402
import test_bft_files as F  # noqa: E402
import btft  # noqa: E402


def link_packet(seq, pace, stop, trim, gap=None):
    p = struct.pack('<BBb', pace, stop, trim) + (bytes([gap]) if gap is not None else b'')
    return btft.packet(0x18, seq, p)


def stream_packet(seq, first, count, size):
    return btft.packet(0x19, seq, struct.pack('<HHB', first, count, size))


def pieces(raw):
    """Type 0x83 pieces with a good CRC in raw bytes: [(idx, data)]."""
    out, i = [], 0
    while True:
        i = raw.find(b'\xB5\x5B\x83', i)
        if i < 0 or i + 6 > len(raw):
            return out
        ln = raw[i + 5]
        end = i + 8 + ln
        if end <= len(raw) and btft.crc16(raw[i + 2:i + 6 + ln]) == struct.unpack_from('<H', raw, i + 6 + ln)[0]:
            out.append((struct.unpack_from('<H', raw, i + 3)[0], bytes(raw[i + 6:i + 6 + ln])))
            i = end
        else:
            i += 1


def stream(e, link, f, first, count, size, seconds, step=0.01):
    """Send STREAM, run `seconds`, return (answer, pieces, bytes per step list)."""
    start = len(e.ble_rx)
    link.parser = btft.AnswerParser()
    link.seen = start
    e.usart2.rx_feed(stream_packet(f.next_seq(), first, count, size))
    per, last, t = [], start, 0.0
    while t < seconds:
        e.advance(step)
        t += step
        per.append(len(e.ble_rx) - last)
        last = len(e.ble_rx)
    raw = bytes(e.ble_rx[start:])
    ans = btft.AnswerParser().feed(raw)
    return (ans[0] if ans else None), pieces(raw), per, raw


def usart(e):
    return e.usart2.brr, (e.usart2.cr2 >> 12) & 3


def run_tests(image):
    card, expect = F.build_card()
    state0 = F.card_state(card)
    e, link = U.open_page(image, card)
    eeprom0 = bytes(e.m.eeprom)
    f = F.Files(link)
    big = F.BIG[:8192]

    print('F5 STREAM arguments')
    a = link.send(stream_packet(f.next_seq(), 0, 10, 64))
    T.check('nothing staged: 0x22', F.status_of(a) == 0x22, repr(a))
    a = f.read('BIG.BIN', 0, 8192)
    T.check('READ 8192 of BIG.BIN: status 0, CRC-32', F.status_of(a) == 0 and a.field == 8192
            and struct.unpack('<I', a.data[:4])[0] == zlib.crc32(big), repr(a))
    for size in (0, 233):
        a = link.send(stream_packet(f.next_seq(), 0, 1, size))
        T.check('size %d: 0x22' % size, F.status_of(a) == 0x22, repr(a))
    a = link.send(stream_packet(f.next_seq(), 128, 1, 64))
    T.check('first beyond the end (128 x 64 = 8192): 0x22', F.status_of(a) == 0x22, repr(a))
    a = link.send(btft.packet(0x19, f.next_seq(), b'\x00\x00\x01'))
    T.check('short payload: 0x22', F.status_of(a) == 0x22, repr(a))
    ans, got, _, _ = stream(e, link, f, 80, 100, 100, 0.5)
    T.check('count cut at the end: field 2 (pieces 80, 81 of 100 bytes)', ans is not None and ans.field == 2, repr(ans))
    T.check('pieces 80 and 81, the last 92 bytes long', [(i, len(d)) for i, d in got] == [(80, 100), (81, 92)]
            and got[1][1] == big[8100:], repr([(i, len(d)) for i, d in got]))

    print('F1 STREAM with the defaults of the page')
    ans, got, per, raw = stream(e, link, f, 0, 200, 64, 8.0)
    T.check('answer first: status 0, field 128', ans is not None and ans.status == 0 and ans.field == 128
            and raw.find(b'\xB5\x5B\x82') < raw.find(b'\xB5\x5B\x83'), repr(ans))
    T.check('128 pieces in order, each once', [i for i, _ in got] == list(range(128)), '%d pieces' % len(got))
    T.check('reassembled = the file bytes', b''.join(d for _, d in got) == big)
    busy = [n for n in per if n]
    rate = sum(per) / (len(busy) * 0.01)
    win = max(sum(per[k:k + 10]) for k in range(len(per) - 9))
    print('    defaults: %d bytes at %.0f bytes/s, at most %d bytes in 100 ms' % (len(raw), rate, win))
    T.check('defaults of the page (pace 13, idle frame every 2 bytes): 1100 .. 1300 bytes/s, at most 143 bytes in '
            'any 100 ms (%.0f, %d)' % (rate, win), 1100 <= rate <= 1300 and win <= 143)

    print('F2 LINK pace 12')
    brr0, stop0 = usart(e)
    a = link.send(link_packet(f.next_seq(), 12, 1, 0))
    T.check('LINK answered, field = BRR %d' % brr0, F.status_of(a) == 0 and a.field == brr0, repr(a))
    ans, got, per, raw = stream(e, link, f, 0, 128, 64, 12.0)
    T.check('128 pieces, reassembled = the file bytes', [i for i, _ in got] == list(range(128))
            and b''.join(d for _, d in got) == big, '%d pieces' % len(got))
    win = max(sum(per[k:k + 10]) for k in range(len(per) - 9))
    T.check('at most 12 bytes per 10 ms tick: at most 11 ticks of bytes in any 100 ms (max %d)' % win, win <= 132)
    busy = [n for n in per if n]
    rate = sum(per) / (len(busy) * 0.01)
    print('    paced: %d bytes in %.2f s = %.0f bytes/s' % (sum(per), len(busy) * 0.01, rate))
    T.check('paced rate 1000 .. 1300 bytes/s', 1000 <= rate <= 1300, '%.0f' % rate)

    print('F3 LINK stop bits and trim')
    a = link.send(link_packet(f.next_seq(), 12, 2, 3))
    T.check('LINK stop 2 trim +3: field = BRR + 3', F.status_of(a) == 0 and a.field == brr0 + 3, repr(a))
    e.advance(0.2)
    T.check('USART2 BRR + 3 and 2 stop bits', usart(e) == (brr0 + 3, 2), repr(usart(e)))
    a = f.ask(btft.info_packet)
    T.check('requests still answered with the new format', F.status_of(a) == 0, repr(a))
    for bad in ((65, 1, 0), (12, 3, 0), (12, 0, 0), (12, 1, 33), (12, 1, -33)):
        a = link.send(link_packet(f.next_seq(), *bad))
        T.check('LINK %r refused (0x22)' % (bad,), F.status_of(a) == 0x22, repr(a))
    e.advance(0.2)
    T.check('refusals change nothing', usart(e) == (brr0 + 3, 2), repr(usart(e)))
    a = link.send(link_packet(f.next_seq(), 0, 1, 0))
    e.advance(0.2)
    T.check('trim 0, 1 stop bit, unpaced: start values again', F.status_of(a) == 0 and usart(e) == (brr0, stop0),
            repr(usart(e)))

    print('F7 idle gaps')
    for gap in (1, 2, 4):
        a = link.send(link_packet(f.next_seq(), 12, 2, 0, gap))
        e.advance(0.2)
        ans, got, per, raw = stream(e, link, f, 0, 128, 64, 14.0)
        busy = [n for n in per if n]
        rate = sum(per) / (len(busy) * 0.01)
        ok = [i for i, _ in got] == list(range(128)) and b''.join(d for _, d in got) == big
        T.check('gap %d, 2 stop bits, pace 12: complete and equal (%.0f bytes/s)' % (gap, rate), ok, '%d pieces' % len(got))
        print('    gap %d: %.0f bytes/s' % (gap, rate))
    a = link.send(link_packet(f.next_seq(), 12, 1, 0, 33))
    T.check('gap 33 refused (0x22)', F.status_of(a) == 0x22, repr(a))
    a = link.send(link_packet(f.next_seq(), 0, 1, 0, 0))
    e.advance(0.2)
    T.check('back to the start values', usart(e) == (brr0, stop0), repr(usart(e)))

    print('F4 a request ends a stream')
    link.send(link_packet(f.next_seq(), 4, 1, 0))           # slow: the stream is still running when LIST comes
    start = len(e.ble_rx)
    e.usart2.rx_feed(stream_packet(f.next_seq(), 0, 128, 64))
    e.advance(1.0)
    e.usart2.rx_feed(btft.list_packet(f.next_seq(), 0))
    e.advance(3.0)
    raw = bytes(e.ble_rx[start:])
    got = pieces(raw)
    ans = btft.AnswerParser().feed(raw)
    lst = raw.rfind(b'\xB5\x5B\x82')
    T.check('LIST answered during the stream', len(ans) == 2 and ans[1].status == 0, repr(ans))
    T.check('stream ended: %d pieces, none after the LIST answer' % len(got),
            0 < len(got) < 128 and raw.find(b'\xB5\x5B\x83', lst) < 0)
    link.send(link_packet(f.next_seq(), 0, 1, 0))

    print('F6 nothing else changed')
    T.check('data EEPROM unchanged', bytes(e.m.eeprom) == eeprom0)
    e.close() if hasattr(e, 'close') else None
    T.check('card unchanged', F.card_state(card) == state0)


def main(argv):
    image = argv[0] if argv else os.path.join(T.ROOT, 'firmware', 'build', 'EEVBlog.bin')
    run_tests(image)
    print('RESULT', ('FAIL: ' + ', '.join(T.fails)) if T.fails else 'ALL PASS', flush=True)
    return 1 if T.fails else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
