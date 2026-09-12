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
    v = struct.unpack(">Q", TEL[64:72])[0] & 0xFFFFFFFF
    hcnt = (v >> 16) & 0x1FF
    acc = (v >> 8) & 0xFF
    rej = v & 0xFF
    # the display window opens 73 dots after the resync point, so H_CNT - 0x1CE is the displacement
    disp = hcnt - 0x1CE
    if disp < -256:
        disp += 512
    elif disp > 256:
        disp -= 512
    print("  0x%03X        %3d    %3d       %+d px%s"
          % (hcnt, acc, rej, disp, "   LOCKED" if hcnt == 0x1CE else "   OUT OF LOCK"))
    sys.stdout.flush()
    time.sleep(gap)
