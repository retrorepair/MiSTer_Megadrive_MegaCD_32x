#!/usr/bin/env python3
"""Stop a blanked 32X from painting over the Mega Drive's backdrop.

The 32X sits in the video path and decides per pixel whether the screen shows its own output or the
Mega Drive's, via /YS. srg320's expression is

    YSO_N = ~((PRI ^ PIX_COLOR[15]) & |MODE) & YS_N_SYNC

MODE is the 32X VDP's bitmap mode, and 0 means blanked - no 32X software running, which is the normal
state for a Mega CD disc or a plain Mega Drive cartridge in this combined core. With MODE = 0 the first
term is 0 and the expression collapses to YSO_N = YS_N_SYNC, so EVERY Mega Drive backdrop pixel selects
the 32X's output instead. The 32X has nothing to draw, so that output is black.

Measured on hardware: on the Mega CD BIOS, whose backdrop is lilac, one scanline at the top of the
picture turns black on alternate frames. Turning the 32X overlay off with the core's debug switch makes
it disappear; upstream's Mega CD core, which has no 32X in the video path, never shows it. Cartridges
look fine only because their backdrop is already black, so replacing it with black is invisible.

A 32X whose VDP is blanked passes the Mega Drive picture through untouched, so YSO_N must be inactive
whenever MODE is 0.
Usage: phase10_ys_gate.py <core dir>"""
import sys, os
d = sys.argv[1]
p = os.path.join(d, "rtl/S32X/VDP.sv")
s = open(p, encoding="utf-8", errors="replace").read()

old = "	assign YSO_N = ~((PRI ^ PIX_COLOR[15]) & |MODE) & YS_N_SYNC;"
new = """	// A blanked 32X VDP (MODE = 0) has no pixel to show, so it must not replace the Mega Drive's.
	// Without the `| ~|MODE` this collapses to YSO_N = YS_N_SYNC and every Mega Drive BACKDROP pixel
	// selects the 32X output, which is black - a one-scanline black bar across the Mega CD BIOS
	// border on alternate frames. See tools/phase10_ys_gate.py for the measurement.
	assign YSO_N = ~((PRI ^ PIX_COLOR[15]) & |MODE) & (YS_N_SYNC | ~|MODE);"""
assert old in s, "anchor missing in VDP.sv"
open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
print("rtl/S32X/VDP.sv ok")
