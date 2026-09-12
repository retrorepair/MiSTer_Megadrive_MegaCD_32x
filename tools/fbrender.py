#!/usr/bin/env python3
"""Render a dumped 32X frame buffer the way the hardware is supposed to, and say where the picture is.

Pairs with tools/mister/ntshot.py, which captures the screen and both frame buffers at the same
instant. The renderer is deliberately independent of the core: it reads the 256-word line table at
the top of the buffer and follows each entry to that line's pixels, exactly as the 32X spec
describes, so what comes out is what the MD actually put in memory. Comparing it against the
screenshot taken alongside separates "drawn wrong" from "displayed wrong".

Usage: fbrender.py <fb.bin> <out.png>"""
import struct
import sys

from PIL import Image


def unswizzle(raw):
    """DDR3 beat order -> 32X word order.

    The FPGA packs four 16-bit words into each 64-bit beat with word 0 in bits 63:48, so an ARM
    reading the same bytes little-endian gets the four words backwards. Undo it once, here.
    """
    out = bytearray(len(raw))
    for i in range(0, len(raw) - 7, 8):
        w = struct.unpack("<4H", raw[i:i + 8])
        struct.pack_into(">4H", out, i, w[3], w[2], w[1], w[0])
    return bytes(out)


src, out = sys.argv[1], sys.argv[2]
d = unswizzle(open(src, "rb").read())
tab = struct.unpack(">256H", d[:0x200])

W, H = 320, 224
img = Image.new("RGB", (W, H))
px = img.load()

ends = []
for y in range(H):
    base = tab[y] * 2                 # the entry is a word offset into the buffer
    last = -1
    for x in range(W):
        o = base + x
        v = d[o] if o < len(d) else 0
        px[x, y] = (v, v, v)          # palette indices as a ramp: this is about geometry, not colour
        if v:
            last = x
    if last >= 0:
        ends.append(last)

img.save(out)

strides = [tab[y + 1] - tab[y] for y in range(40, 200)]
common = max(set(strides), key=strides.count)
print("line table: [0]=%04X [40]=%04X [41]=%04X [223]=%04X   commonest stride=%d words (%d px)"
      % (tab[0], tab[40], tab[41], tab[223], common, common * 2))
ends.sort()
if ends:
    print("lines with data: %d of %d   rightmost non-zero pixel: median %d, max %d"
          % (len(ends), H, ends[len(ends) // 2], ends[-1]))
else:
    print("frame is entirely zero")
