#!/usr/bin/env python3
"""Add CRAM dots, the real Mega Drive artefact, behind an OSD switch defaulted off.

On real hardware, writing the colour RAM while the raster is in the active display puts the value being
written straight onto the screen for that pixel - a coloured dot. Programs that change the palette
mid-frame produce a visible speckle. The older VHDL VDP models this and exposes it as an option:

    CRAM_DATA <= CRAM_D_A when CRAM_WE_A = '1' and CRAM_DOTS = '1' else CRAM_Q_B;   -- vdp.vhd:838

The SystemVerilog VDP this core uses has no such path, so the artefact never appears. This adds the same
mux at the point where the display colour enters the pixel pipeline, gated by a new input so it is inert
unless switched on. Bit 10 is the same status bit the old Mega CD core used for it, and is otherwise
unused here.

NOTE: dots produced this way sit still in SCREEN space. They are not the same thing as wrong pixel
values inside graphics data, which travel with the picture - see tools/phase11_as_select.py for that.
Usage: phase13_cram_dots.py <core dir>"""
import sys, os
d = sys.argv[1]

def edit(rel, pairs):
    p = os.path.join(d, rel)
    s = open(p, encoding="utf-8", errors="replace").read()
    for old, new in pairs:
        assert old in s, rel + ": anchor missing: " + old[:70]
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(s)
    print(rel, "ok")

edit("rtl/GEN/vdp.sv", [
("	input             BORDER_EN,", "	input             BORDER_EN,\n	input             CRAM_DOTS,	// real hardware shows the value being written to CRAM as a dot"),
("					PIX_COL_PIPE[0] <= CRAM_Q_A;",
 """					// CRAM dots: a colour-RAM write during active display puts the written value on
					// screen for that pixel on real hardware. Mirrors vdp.vhd:838. Off by default.
					PIX_COL_PIPE[0] <= (CRAM_DOTS && CRAM_WE) ? CRAM_D : CRAM_Q_A;"""),
])

edit("rtl/GEN/gen.sv", [
("	.BORDER_EN(BORDER),", "	.BORDER_EN(BORDER),\n	.CRAM_DOTS(CRAM_DOTS),"),
("	input         BORDER,", "	input         BORDER,\n	input         CRAM_DOTS,"),
])

edit("MegaCD.sv", [
("	.BORDER(status[29]),", "	.BORDER(status[29]),\n	.CRAM_DOTS(status[10]),"),
('	"P1OT,Border,No,Yes;",', '	"P1OT,Border,No,Yes;",\n	"P1OA,CRAM Dots,Off,On;",'),
])
