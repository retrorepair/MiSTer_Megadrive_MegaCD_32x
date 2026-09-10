#!/usr/bin/env python3
"""Add a plain "Reset" to the OSD: the console's own reset button, not a power cycle.

The entry exists in the upstream Mega CD cores but was commented out when this core's top level was
assembled (`//"R1,Reset;"`), so the only reset available here is "Reset & Eject CD", which resets
everything including the Mega CD.

On real hardware, pressing reset on a Mega Drive with a Mega CD attached resets the Mega Drive and
whatever is in the cartridge slot, but NOT the Mega CD: the disc keeps spinning and the sub-CPU keeps
running, which is why a CD game comes back to its own title screen rather than to the BIOS. The
NukedMD-based Mega CD core models this distinction explicitly ("A warm reset does NOT reset the CD
block"), so this does the same - the new reset reaches the Mega Drive, the 32X, the cartridge and the
32X's external memory, and leaves the Mega CD alone.

The OSD's R-type entries only pulse their status bit, so the pulse is stretched to about 9.8 ms,
comparable to the reference core's ~9.5 ms hold.
Usage: phase18_soft_reset.py <core dir>
"""
import sys, os

d = sys.argv[1]
p = os.path.join(d, "MegaCD.sv")
s = open(p, encoding="utf-8", errors="replace").read()


def rep(old, new):
    global s
    assert old in s, "anchor missing: " + old[:70]
    s = s.replace(old, new, 1)


# 1. put the menu entry back
rep('\t//"R1,Reset;"', '\t"R1,Reset;",')

# 2. the stretched warm-reset signal
rep(
    "wire reset = RESET | status[0] | cart_remove | buttons[1] | region_set;",
    "wire reset = RESET | status[0] | cart_remove | buttons[1] | region_set;\n"
    "\n"
    '// OSD "Reset" (status[1]): the console\'s own reset button. It resets the Mega Drive, the 32X and\n'
    "// the cartridge, and deliberately does NOT touch the Mega CD - on real hardware the disc keeps\n"
    "// spinning and the sub-CPU keeps running, so a CD game returns to its own title screen instead of\n"
    "// to the BIOS. R-type OSD entries only pulse their bit, so stretch it to ~9.8 ms (the reference\n"
    "// core holds ~9.5 ms). See tools/phase18_soft_reset.py.\n"
    "reg [18:0] soft_reset_cnt = 0;\n"
    "wire       soft_reset = |soft_reset_cnt;\n"
    "always @(posedge clk_sys) begin\n"
    "\treg old_soft;\n"
    "\told_soft <= status[1];\n"
    "\tif (~old_soft & status[1]) soft_reset_cnt <= '1;\n"
    "\telse if (|soft_reset_cnt)  soft_reset_cnt <= soft_reset_cnt - 1'd1;\n"
    "end",
)

# 3. route it to the Mega Drive, the 32X, the cartridge and the 32X's DDR3 memory - NOT the Mega CD.
#    Each anchor carries the following line so it is unique in the file.
rep("\t.RESET_N(~reset),\n\t.MCLK(clk_sys),", "\t.RESET_N(~(reset | soft_reset)),\n\t.MCLK(clk_sys),")
rep(
    "\t.RST_N(~(reset | rom_download)),\n\t.SH2_DIV2(status[2]),",
    "\t.RST_N(~(reset | soft_reset | rom_download)),\n\t.SH2_DIV2(status[2]),",
)
rep(
    "\t.RST_N(~(reset | rom_download)),\n\n\t.VCLK(GEN_VCLK_CE),",
    "\t.RST_N(~(reset | soft_reset | rom_download)),\n\n\t.VCLK(GEN_VCLK_CE),",
)
rep("\t.reset(reset | rom_download),", "\t.reset(reset | soft_reset | rom_download),")

open(p, "w", encoding="utf-8").write(s)
print("MegaCD.sv ok")
