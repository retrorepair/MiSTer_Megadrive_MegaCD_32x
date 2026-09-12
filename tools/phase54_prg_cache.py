#!/usr/bin/env python3
"""Put a read cache on the Mega CD PRG-RAM SDRAM port.

WHY
The four remaining mcd-verificator failures (VAR TESTS 02, IRQ TEST 09, REG 8030 07, CDC FLAGS 40)
are one cause: the main 68000's cartridge instruction fetches contend with the Mega CD sub-CPU's
PRG-RAM reads on the shared SDRAM controller. Measured, the sub-CPU takes 13.7% of the controller,
which costs ~1.7% of a 521 ns 68000 bus cycle; with ~0.9% of refresh that is the ~2.6% CDC FLAGS is
short of. The sub-CPU's working set is ~50 distinct words (scratch/subhist.py), so a small cache
removes nearly all of that traffic without touching DDR3 - which was rejected, correctly, because
the SDRAM is on the board for deterministic latency.

WHAT IT DOES NOT DO
A hit is held busy as long as an uncontended miss, so the Mega CD sees the latency it sees today.
Only the SDRAM slot disappears.

SAFETY
All three PRG-RAM writers - sub-CPU, the MD's gate-array window at $420000, CDC DMA - are already
arbitrated onto this one port inside ASIC.vhd, and no other SDRAM port addresses the region, so the
cache sees every write. See the header of core/rtl/prg_cache.sv.

Usage: phase54_prg_cache.py <core dir>"""
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


edit("MegaCD.qsf", [
    ("set_global_assignment -name SYSTEMVERILOG_FILE rtl/sdram.sv",
     "set_global_assignment -name SYSTEMVERILOG_FILE rtl/sdram.sv\n"
     "set_global_assignment -name SYSTEMVERILOG_FILE rtl/prg_cache.sv"),
])

edit("MegaCD.sv", [
    # the port used to be wired straight through: MCD <-> sdram port 2
    ("""assign MCD_PRG_BUSY = sdr_busy;
assign MCD_PRG_DI   = sdr_do;""",
     """// Mega CD PRG-RAM read cache (core/rtl/prg_cache.sv, tools/phase54_prg_cache.py). The sub-CPU
// re-reads about fifty words; every hit is one SDRAM slot the MD's cartridge fetches stop losing,
// which is the 2.6% the mcd-verificator timing tests are short of. Writes still go straight to the
// SDRAM, and every PRG-RAM writer reaches it through this one port, so the cache cannot go stale.
wire [24:1] prgc_a;
wire [15:0] prgc_din;
wire        prgc_rd, prgc_wrl, prgc_wrh;

prg_cache #(.IDX(9)) prg_cache
(
	.clk(clk_ram),
	.reset(reset),

	.a({(MCD_BANK23 ? 6'b100000 : 6'b011111),MCD_PRG_ADDR}),
	.din(MCD_PRG_DO),
	.dout(MCD_PRG_DI),
	.rd(~MCD_PRG_OE_N),
	.wrl(~MCD_PRG_WRL_N),
	.wrh(~MCD_PRG_WRH_N),
	.busy(MCD_PRG_BUSY),

	.s_a(prgc_a),
	.s_din(prgc_din),
	.s_dout(sdr_do),
	.s_rd(prgc_rd),
	.s_wrl(prgc_wrl),
	.s_wrh(prgc_wrh),
	.s_busy(sdr_busy)
);"""),

    ("""	//MCD PRG-RAM: banks 2,3
	.addr2({(MCD_BANK23 ? 6'b100000 : 6'b011111),MCD_PRG_ADDR}), // 1000000-107FFFF / 0F80000-0FFFFFF
	.din2(MCD_PRG_DO),
	.dout2(sdr_do),
	.rd2(~MCD_PRG_OE_N),
	.wrl2(~MCD_PRG_WRL_N),
	.wrh2(~MCD_PRG_WRH_N),
	.busy2(sdr_busy),""",
     """	//MCD PRG-RAM: banks 2,3 - behind the read cache above (1000000-107FFFF / 0F80000-0FFFFFF)
	.addr2(prgc_a),
	.din2(prgc_din),
	.dout2(sdr_do),
	.rd2(prgc_rd),
	.wrl2(prgc_wrl),
	.wrh2(prgc_wrh),
	.busy2(sdr_busy),"""),
])
