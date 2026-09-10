#!/usr/bin/env python3
"""Give the Mega CD's PRG-RAM port priority over the cartridge port, as an alternative to early DTACK.

Early DTACK (OSD bit 28) makes mcd-verificator VAR TESTS pass, but it works by acknowledging the
sub-CPU before the data has arrived, which is only safe if the SDRAM always answers inside the CPU's
latch window. Measured here it does not: PRG-RAM reads run 5 to 18 clk_sys because sdram.sv serves
five ports at FIXED priority 0 > 1 > 2 > 3 > 4 and the Mega CD PRG-RAM sits on port 2, below the
cartridge port that the MD 68000 and both SH-2s share.

This attacks the same problem from the other end: leave the acknowledge where it is (on the data, which
can never be stale) and remove the contention that makes the read late. Priority becomes

    2 (MCD PRG-RAM) > 0 (cartridge) > 1 (MCD BIOS ROM) > 3 (PCM) > 4 (load/save)

which is also the better match to the hardware. On a real machine PRG-RAM and the cartridge are
entirely separate memories and neither can stall the other; when a shared controller has to pick, the
tighter deadline should win, and the sub-CPU's is tighter than the main CPU's - 12.5 MHz gives it
120 ns from /AS to the /DTACK sample where the 7.67 MHz main CPU has 195 ns.

OSD bit 26 selects it at run time so it can be A/B'd against bit 28 and against both together.

Usage: phase21_prg_priority.py <core dir>"""
import sys, os

d = sys.argv[1]


def edit(rel, pairs):
    p = os.path.join(d, rel)
    s = open(p, encoding="utf-8", errors="replace").read()
    for old, new in pairs:
        assert old in s, rel + ": anchor missing: " + old[:70]
        assert s.count(old) == 1, rel + ": anchor not unique: " + old[:70]
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8", newline="").write(s)
    print(rel, "ok")


edit("MegaCD.sv", [
    ('\t"H2O[27],PRG Lat Thresh,Wait(>6),Hazard(>9);",',
     '\t"H2O[27],PRG Lat Thresh,Wait(>6),Hazard(>9);",\n\t"H2O[26],MCD PRG Priority,Normal,Above Cart;",'),
    ("""	.busy4(tmpram_busy)
);""",
     """	.busy4(tmpram_busy),

	// See tools/phase21_prg_priority.py: lift the Mega CD PRG-RAM above the cartridge port so its
	// read latency stops depending on what the MD 68000 and the SH-2s are doing.
	.prg_first(status[26])
);"""),
])

edit("rtl/sdram.sv", [
    ("""	output            busy4
);""",
     """	output            busy4,

	// Fixed priority is 0 > 1 > 2 > 3 > 4. With prg_first the Mega CD PRG-RAM (port 2) is served
	// ahead of the cartridge (port 0) and the BIOS ROM (port 1): the sub-CPU runs at 12.5 MHz and
	// has 120 ns from /AS to its /DTACK sample, against 195 ns for the 7.67 MHz main CPU, so when
	// one of them has to wait it should be the one with the slack. See tools/phase21_prg_priority.py.
	input             prg_first
);"""),
    # old_rd/old_wr are declared INSIDE the always block, so the port-2 test has to be written out
    # in each guard rather than hoisted to a module-level wire.
    ("""		else if ((~old_rd[0] && rd[0]) || (~old_wr[0] && wr[0])) begin""",
     """		// Step over the cartridge port when the Mega CD PRG-RAM has a request waiting and
		// prg_first is set - that is all it takes to reorder a fixed-priority else-if chain.
		else if (((~old_rd[0] && rd[0]) || (~old_wr[0] && wr[0]))
		         && !(prg_first && ((~old_rd[2] && rd[2]) || (~old_wr[2] && wr[2])))) begin"""),
    ("""		else if ((~old_rd[1] && rd[1]) || (~old_wr[1] && wr[1])) begin""",
     """		else if (((~old_rd[1] && rd[1]) || (~old_wr[1] && wr[1]))
		         && !(prg_first && ((~old_rd[2] && rd[2]) || (~old_wr[2] && wr[2])))) begin"""),
])
