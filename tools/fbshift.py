#!/usr/bin/env python3
"""Measure how far the 32X layer is displaced horizontally from what is in the frame buffer.

Takes the pairs tools/mister/ntshot.py captures - a screenshot and the DDR3 frame buffer grabbed at
the same instant - and, for each line, finds the horizontal offset at which the screen best matches
the memory. A correct core returns the same small positive number on every line (the screenshot's
own border width) for every capture. Night Trap does not.

Usage: fbshift.py <prefix> ...      e.g. fbshift.py scratch/nt2/00 scratch/nt2/01"""
import struct
import sys

from PIL import Image

DY = 11          # the screenshot's top border, measured against a known-good cart 32X capture


def unswizzle(raw):
    """DDR3 beat order -> 32X word order: four words per 64-bit beat, word 0 at bits 63:48."""
    out = bytearray(len(raw))
    for i in range(0, len(raw) - 7, 8):
        w = struct.unpack("<4H", raw[i:i + 8])
        struct.pack_into(">4H", out, i, w[3], w[2], w[1], w[0])
    return bytes(out)


for pre in sys.argv[1:]:
    d = unswizzle(open(pre + "_fb0.bin", "rb").read())
    tab = struct.unpack(">256H", d[:0x200])
    im = Image.open(pre + "_screen.png").convert("RGB")
    W, H = im.size
    px = im.load()

    votes = {}
    for y in range(0, 224, 16):
        sy = y + DY
        if sy >= H:
            continue
        b = tab[y] * 2
        mr = [1 if (b + x < len(d) and d[b + x]) else 0 for x in range(320)]
        if sum(mr) < 30:
            continue
        sr = [1 if sum(px[x, sy]) > 40 else 0 for x in range(W)]
        best = None
        for dx in range(-160, 161):
            inter = union = 0
            for x in range(320):
                sx = x + dx
                a = mr[x]
                bb = sr[sx] if 0 <= sx < W else 0
                if a or bb:
                    union += 1
                    if a and bb:
                        inter += 1
            if union > 20:
                s = inter / union
                if best is None or s > best[0]:
                    best = (s, dx)
        if best and best[0] > 0.55:
            votes[best[1]] = votes.get(best[1], 0) + 1

    if not votes:
        print("%s  no line had enough content to align" % pre)
    else:
        dx = max(votes, key=votes.get)
        # +14 is a correctly placed layer: the screenshot's own left border
        print("%s  dx=%+d on %d/%d lines   -> 32X layer displaced %+d px"
              % (pre, dx, votes[dx], sum(votes.values()), dx - 14))
