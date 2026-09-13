#!/usr/bin/env python3
"""Read the 32X horizontal lock out of telemetry beat 8, live.

Pairs with tools/phase65_hsync_relock.py. Beat 8 (HPS 0x30200040) carries, in its low 32 bits:

    [24:16] H_CNT captured at the last HSYNC falling edge
    [15: 8] HSYNC edges TAKEN, saturating at 255
    [ 7: 0] HSYNC edges REFUSED by the guard, saturating at 255

A locked 32X reads H_CNT = 0x1CE with TAKEN climbing and REFUSED at zero. The Night Trap fault reads
an H_CNT well below 0x160 - the accept window - with REFUSED saturated and TAKEN stuck, and the layer
displaced by (H_CNT - 0x1CE) dots, which is what tools/fbshift.py measures optically.

Usage: hlock.py [samples] [gap-secs]"""
import mmap
import os
import struct
import sys
import time

n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
gap = float(sys.argv[2]) if len(sys.argv) > 2 else 1.0

fr = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
TEL = mmap.mmap(fr, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30200000)

print("  H_CNT@HSYNC  taken  refused   implied displacement")
for i in range(n):
    # DDR3 packs four 16-bit words per beat with word 0 at bits 63:48, so the HPS sees the words
    # reversed: bytes 0..3 are DBG_SYNC[15:0] then DBG_SYNC[31:16], each little-endian.
    raw = TEL[64:72]
    lo = raw[0] | (raw[1] << 8)
    hi = raw[2] | (raw[3] << 8)
    hcnt = hi & 0x1FF
    acc = (lo >> 8) & 0xFF
    rej = lo & 0xFF
    # the display window opens 72 dots after the resync point, so H_CNT - 0x1CE is the displacement
    disp = hcnt - 0x1CE
    if disp < -256:
        disp += 512
    elif disp > 256:
        disp -= 512
    print("  0x%03X        %3d    %3d       %+d px%s"
          % (hcnt, acc, rej, disp, "   LOCKED" if hcnt == 0x1CE else "   OUT OF LOCK"))
    sys.stdout.flush()
    time.sleep(gap)
