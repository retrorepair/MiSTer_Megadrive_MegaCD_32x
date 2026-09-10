#!/usr/bin/env python3
"""Decode the 68000 exception stack frame captured by tools/phase9_faultframe.py. Runs ON the MiSTer.

On a group-0 exception (bus or address error) the 68000 writes its frame highest address first, so the
ring of the last eight writes, frozen when it fetched the fault vector, reads back newest first as:
    w1 special status word   w2 access address high   w3 access address low   w4 instruction register
    w5 status register       w6 program counter high  w7 program counter low
Anything after that is whatever the program was writing before it faulted.
"""
import mmap, os

fd = os.open('/dev/mem', os.O_RDONLY | os.O_SYNC)
mm = mmap.mmap(fd, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30200000)
def beat(o): return int.from_bytes(mm[o:o + 8], 'little')

VEC = {0x08: 'BUS ERROR', 0x0C: 'ADDRESS ERROR'}
s, h2 = beat(0x10), beat(0x20)
t, t2 = beat(0x28), beat(0x30)
a, b = beat(0x38), beat(0x40)
w = [(a >> 48) & 0xFFFF, (a >> 32) & 0xFFFF, (a >> 16) & 0xFFFF, a & 0xFFFF,
     (b >> 48) & 0xFFFF, (b >> 32) & 0xFFFF, (b >> 16) & 0xFFFF, b & 0xFFFF]

print('trail (oldest->newest): $%06X $%06X $%06X $%06X'
      % (t2 & 0xFFFFFF, (t2 >> 24) & 0xFFFFFF, t & 0xFFFFFF, (t >> 24) & 0xFFFFFF))
v = (h2 >> 24) & 0xFFFFFF
print('last vector-table access: $%06X  %s' % (v, VEC.get(v & ~3, '')))
print('writes newest->oldest: ' + ' '.join('%04X' % x for x in w))

if any(w):
    ssw, fa = w[0], (w[1] << 16) | w[2]
    ir, sr, pc = w[3], w[4], (w[5] << 16) | w[6]
    print()
    print('  special status  %04X   R/W=%s  I/N=%s  FC=%d'
          % (ssw, 'read' if (ssw >> 4) & 1 else 'WRITE',
             'instruction' if not ((ssw >> 3) & 1) else 'not-instruction', ssw & 7))
    print('  FAULT ADDRESS   $%08X   %s' % (fa, 'ODD' if fa & 1 else 'even'))
    print('  opcode (IR)     %04X' % ir)
    print('  SR              %04X' % sr)
    print('  PC at fault     $%08X' % pc)
print('stall seen %d at $%06X  give-ups %d' % ((s >> 18) & 1, (s >> 24) & 0xFFFFFF, h2 & 0xFFFF))
