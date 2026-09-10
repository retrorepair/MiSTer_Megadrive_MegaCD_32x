#!/usr/bin/env python3
"""Stop the VDP displaying one extra scanline at the top of the picture.

MEASURED: on the Mega CD BIOS at PAL with borders on (346x294), output row 37 - the last row of the top
border - alternates between a border row and a picture row from frame to frame. Every other border row
is static across 24 captured frames. The upstream Mega CD core, which uses the older VHDL VDP, shows
zero toggling in its top border across 18 frames.

CAUSE, from reading both VDPs side by side:
`vdp.sv` decides border-versus-picture with `DISP_EN_PIPE[0] <= MR2.DISP & ~IN_VBL` (vdp.sv:1672), and
clears IN_VBL when V_CNT rolls 0x1FE->0x1FF (vdp.sv:882-883). So the first displayed active line is
V_CNT = 0x1FF, "line -1", and the picture is 225 lines instead of 224. With PAL, V28 and the border
enabled, output row 0 is V_CNT 0x1DA, so row 37 is exactly V_CNT 0x1FF and row 38 is V_CNT 0x000 - which
is the row that was measured toggling.

IN_VBL is the CPU-visible vertical-blank flag and is also used to gate the VDP's slot allocation; it is
correct that it clears there. The mistake is reusing it for the on-screen border decision. The older
VHDL VDP keeps a separate signal for exactly this, `V_ACTIVE_DISP`, asserted only for HV_VCNT
0x000..V_DISP_HEIGHT-1, so line 0x1FF renders for sprite prefetch but is DISPLAYED as border
(vdp.vhd:2424-2429 and :2668).

WHY IT ALTERNATES rather than being steady: the only per-frame-variable term in that expression is
MR2.DISP, VDP register 1 bit 6, which the 68000 can write at any time and which is sampled once per
line at H_CNT = 0x013. For row 37 that instant falls right at the tail of the BIOS's vertical-blank
work, so a write to register 1 landing either side of it flips this one line and nothing else.

Line 0x1FF is still rendered - only its display is suppressed, matching the old VDP.
Usage: phase12_disp_line.py <core dir>"""
import sys, os
d = sys.argv[1]
p = os.path.join(d, "rtl/GEN/vdp.sv")
s = open(p, encoding="utf-8", errors="replace").read()

old = """				if ((H_CNT == 9'h013 && !H40) || (H_CNT == 9'h013 && H40))
					DISP_EN_PIPE[0] <= MR2.DISP & ~IN_VBL;"""
new = """				if ((H_CNT == 9'h013 && !H40) || (H_CNT == 9'h013 && H40))
					// V_CNT 0x1FF is "line -1": IN_VBL has already cleared for it, but it is a rendering
					// line (sprite prefetch), not a displayed one. Showing it makes the picture 225 lines
					// and puts a border row's worth of picture at the top, which flickers because
					// MR2.DISP is sampled here right at the tail of the BIOS's vblank work. The older
					// VHDL VDP keeps a separate V_ACTIVE_DISP for this and starts it at V_CNT 0.
					// See tools/phase12_disp_line.py.
					DISP_EN_PIPE[0] <= MR2.DISP & ~IN_VBL & (V_CNT != 9'h1FF);"""
assert old in s, "anchor missing in vdp.sv"
open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
print("rtl/GEN/vdp.sv ok")
