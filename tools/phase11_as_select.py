#!/usr/bin/env python3
"""Make the strobe the Mega CD gate array sees switchable, so one build can test both wirings.

ASIC.vhd ends a Word RAM read with

    if EXT_AS_N = '0' then M68K_WORDRAM_DO <= <fresh word>;
    else                   M68K_WORDRAM_DO <= LAST_M68K_WORDRAM_DO;   -- the previously latched one

so whatever drives EXT_AS_N decides, per access, whether the Mega CD hands back the word it just read
or the one before it.

Upstream's Mega CD core feeds the BUS ARBITER's /AS. This project changed it to the 68000's OWN /AS to
cure a corrupt band across the BIOS logo. That change is suspect: during a VDP DMA out of Word RAM the
68000 is off the bus and its /AS is HIGH, so the gate array returns the stale word for every DMAed
word. On real hardware there is one /AS on the bus and it is driven by whichever master owns it - the
68000 or the VDP during DMA - so the arbiter's /AS is the faithful choice and upstream is right.

The visible symptom now is single wrong pixels that MOVE WITH the Mega CD logo, i.e. wrong words inside
graphics data, which is what a stale-word return produces.

OSD debug bit 39 selects: 0 = the arbiter's /AS (upstream, and what the hardware does), 1 = the 68000's
own /AS (what this project has been shipping). Default 0.
Usage: phase11_as_select.py <core dir>"""
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

edit("MegaCD.sv", [
('	"H2O[2],SH2 Clock,23.0MHz,26.8MHz;",',
 '	"H2O[2],SH2 Clock,23.0MHz,26.8MHz;",\n	"H2O[39],MCD /AS,Bus(hw),68000;",'),
("	.EXT_AS_N(GEN_M68K_AS_N),",
 """	// Which strobe the gate array latches Word RAM data with. The arbiter's /AS is what the hardware
	// presents, because on a real bus /AS is driven by whichever master owns it, the VDP included
	// during DMA. Debug bit 39 switches back to the 68000's own /AS for comparison.
	// See tools/phase11_as_select.py.
	.EXT_AS_N(status[39] ? GEN_M68K_AS_N : GEN_AS_N),"""),
])
