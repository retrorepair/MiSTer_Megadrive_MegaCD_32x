#!/usr/bin/env python3
"""Patch mcd-verificator so CDC FLAGS reports d5 instead of stopping at d4.

CDC FLAGS sub-test 0x40 times the decoder interrupt flag (IFSTAT bit 5, DECI) over one 75 Hz
frame by polling it from the main CPU through the sub-CPU RPC stubs:

    01454A  clr.w   d4                  ; polls while DECI is ASSERTED (bit5 = 0)
    01454C  clr.w   d5                  ; polls while DECI is CLEAR    (bit5 = 1)
    ...
    01459A  move.w  d4, d0
    01459C  addi.w  #$FFD0, d0          ; d0 = d4 - 48
    0145A0  cmpi.w  #$2, d0
    0145A4  bhi.w   $14718              ; FAIL 40 unless d4 in [48, 50]
    0145A8  move.w  d5, d7
    0145AA  addi.w  #$FFB9, d7          ; d7 = d5 - 71
    0145AE  cmpi.w  #$2, d7
    0145B2  bhi.w   $146FC              ; FAIL 41 unless d5 in [71, 73]

49 / (49 + 72) = 40.5%, which is jsgroth's "the decoder interrupt flag should automatically clear
about 40% of the way through a 75Hz frame".

This core reports d4 = 87 and so never reaches the d5 check, and the two candidate causes are not
distinguishable from d4 alone:
  * duty cycle wrong (DEC_MID late or missed)      -> d4 high AND d5 low,  d4 + d5 ~ 121
  * poll loop faster than hardware (main<->sub RPC) -> d4 high AND d5 high, d4 + d5 ~ 220
Widening the d4 bound to always pass makes the run report d5 through error 41, which separates them.

Patch: 0145A0 cmpi.w #$2,d0 -> cmpi.w #$FFFF,d0, so the unsigned BHI can never be taken.
Usage: verif_patch_cdcflags.py <in.bin> <out.bin>
"""
import sys

src, dst = sys.argv[1], sys.argv[2]
d = bytearray(open(src, 'rb').read())

OFF = 0x0145A0
EXPECT = bytes([0x0C, 0x40, 0x00, 0x02])   # cmpi.w #$2,d0

got = bytes(d[OFF:OFF + 4])
assert got == EXPECT, "unexpected bytes at %06X: %s" % (OFF, got.hex())

d[OFF + 2] = 0xFF
d[OFF + 3] = 0xFF

open(dst, 'wb').write(bytes(d))
print("patched %06X: %s -> %s" % (OFF, EXPECT.hex(), bytes(d[OFF:OFF + 4]).hex()))
print("CDC FLAGS will now report d5 as ERROR 41 (expected range 71-73)")
