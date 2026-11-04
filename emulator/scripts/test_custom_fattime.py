"""Unit test of get_fattime (custom build fix CF-04) by direct execution in unicorn: the calendar copy at 0x200080D7
(year from 2000, month, day, hour, minute, second) -> r0 = FAT date << 16 | FAT time, r1..r3 kept.  Any field out of
range must give the fallback 1980-01-01 00:00:00 (0x00210000); v0.9.4 checked only month and day (6 cases fail there).

    python -I emulator/scripts/test_custom_fattime.py [image [map]]   default firmware/build/EEVBlog.bin, 121gw.map
"""
import os
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_MODE_MCLASS
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_SP, UC_ARM_REG_LR

ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..'))
IMAGE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, 'firmware', 'build', 'EEVBlog.bin')
MAP = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(IMAGE), '121gw.map')
addr = None
for line in open(MAP):
    p = line.split()
    if len(p) == 2 and p[1] == 'get_fattime' and p[0].startswith('0x'):
        addr = int(p[0], 16)
assert addr, 'get_fattime not in the map'
img = open(IMAGE, 'rb').read()
CAL = 0x200080D7
RET = 0x08006000 + 0x100000                    # unmapped-free magic return inside a mapped page
u = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
u.mem_map(0x08000000, 0x200000)
u.mem_write(0x08006000, img)
u.mem_write(RET, b'\xfe\xe7')                  # b . (stop address)
u.mem_map(0x20000000, 0x10000)


def fat(y, mo, d, h, mi, s):
    u.mem_write(CAL, bytes([y, mo, d, h, mi, s]))
    for r, v in ((UC_ARM_REG_R1, 0x11111111), (UC_ARM_REG_R2, 0x22222222), (UC_ARM_REG_R3, 0x33333333)):
        u.reg_write(r, v)
    u.reg_write(UC_ARM_REG_SP, 0x2000F000)
    u.reg_write(UC_ARM_REG_LR, RET | 1)
    u.emu_start(addr | 1, RET, count=500)
    kept = (u.reg_read(UC_ARM_REG_R1), u.reg_read(UC_ARM_REG_R2), u.reg_read(UC_ARM_REG_R3)) == \
        (0x11111111, 0x22222222, 0x33333333)
    return u.reg_read(UC_ARM_REG_R0), kept


def want(y, mo, d, h, mi, s):
    return ((y + 20) << 25 | mo << 21 | d << 16 | h << 11 | mi << 5 | s // 2)


fails = []
FALLBACK = 0x00210000
cases = [((26, 11, 3, 18, 45, 30), None), ((0, 1, 1, 0, 0, 0), None), ((99, 12, 31, 23, 59, 59), None),
         ((26, 0, 3, 18, 45, 30), FALLBACK), ((26, 13, 3, 18, 45, 30), FALLBACK), ((26, 11, 0, 18, 45, 30), FALLBACK),
         ((26, 11, 32, 18, 45, 30), FALLBACK), ((26, 11, 3, 24, 45, 30), FALLBACK), ((26, 11, 3, 0x45, 0, 0), FALLBACK),
         ((26, 11, 3, 18, 60, 30), FALLBACK), ((26, 11, 3, 18, 0x99, 30), FALLBACK), ((26, 11, 3, 18, 45, 60), FALLBACK),
         ((100, 11, 3, 18, 45, 30), FALLBACK), ((0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF), FALLBACK)]
for cal, exp in cases:
    exp = want(*cal) if exp is None else exp
    got, kept = fat(*cal)
    ok = got == exp and kept
    print('  %-28s -> 0x%08X want 0x%08X r1-r3 kept=%s %s' % (cal, got, exp, kept, 'ok' if ok else 'FAIL'))
    if not ok:
        fails.append(cal)
print('RESULT', 'FAIL %s' % fails if fails else 'ALL PASS')
sys.exit(1 if fails else 0)
