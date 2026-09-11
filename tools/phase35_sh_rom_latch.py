#!/usr/bin/env python3
"""Latch the SH-2's cartridge ROM word the moment it is valid, not on the next SH-2 clock enable.

WHY
`sdram.sv` has ONE data register shared by all five ports:

    sdram.sv:134  reg [15:0] dout;
    sdram.sv:136  assign dout0 = dout;   ... dout1 ... dout2 ... dout3 ... dout4
    sdram.sv:227  dout <= SDRAM_DQ;      reloaded on ANY port's read completion

Every consumer must latch it on its own handshake. Returning a live wire into it was the r7 root
cause on the Mega Drive cartridge path, and the SH-2 cartridge path has the same shape but worse:

    IF.sv:860   if (!ROM_WAIT && CE_F) begin
    IF.sv:861       SH_ROM_DO <= CDI;

The MD path captures as soon as its wait drops. This one additionally waits for CE_F - the SH-2
clock enable, asserted on only 3 of every 7 clk_sys - so a word that is already valid sits exposed
for up to three clocks while the Mega CD's BIOS ROM (port 1), PRG-RAM (port 2) and PCM (port 3) can
each complete a read and overwrite `dout`. The SH-2 then executes whatever landed there.

That matches the measured symptom exactly: Fusion's master SH-2 intermittently takes a wild jump and
ends up executing the 32X boot ROM's vector table as code, walking into the `BRA .` trap at 0x13C
(trap trail: 060005C0 -> 060005C2 -> 0000013C). And it correlates with contention - trapped in 2 of
3 runs with the disc in (Mega CD ports active) versus 0 of 3 cart-only.

srg320's standalone 32X has the same code and gets away with it: that core has no Mega CD ports
competing for the shared register. This is a latent upstream race that only bites in the tower.

THE FIX
Capture CDI on the first cycle the word is valid and hold it until the SH-2 clock edge consumes it,
so the value the SH-2 sees can never be a later port's data. The state machine still advances on
CE_F exactly as before, so SH-2 bus timing is unchanged.

Usage: phase35_sh_rom_latch.py <core dir>"""
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


edit("rtl/S32X/IF.sv", [
    ("""	bit [15:0] SH_ROM_DO;""",
     """	bit [15:0] SH_ROM_DO;
	bit        SH_ROM_CAP;		// the ROM word has been captured for this access (phase35)"""),
    ("""				RS_SH_RW: begin
					if (CE_F) begin
						ROM_ST <= RS_SH_WAIT;
					end
				end""",
     """				RS_SH_RW: begin
					SH_ROM_CAP <= 0;
					if (CE_F) begin
						ROM_ST <= RS_SH_WAIT;
					end
				end"""),
    ("""				RS_SH_READ: begin
					if (!ROM_WAIT/*_SYNC*/ && CE_F) begin
						SH_ROM_DO <= CDI/*_SYNC*/;
						SH_ROM_WAIT <= 0;""",
     """				RS_SH_READ: begin
					// sdram.sv shares ONE dout register across all five ports (sdram.sv:134-140), so the
					// word is only ours until the next port completes a read. Capture it the instant it
					// is valid rather than waiting for CE_F, which is asserted on just 3 of every 7
					// clk_sys and left the value exposed for up to three clocks - long enough for the
					// Mega CD's BIOS ROM, PRG-RAM or PCM port to overwrite it and feed the SH-2 a wrong
					// instruction. Same root cause as the r7 Mega Drive cartridge fix.
					if (!ROM_WAIT && !SH_ROM_CAP) begin
						SH_ROM_DO <= CDI;
						SH_ROM_CAP <= 1;
					end
					if (!ROM_WAIT/*_SYNC*/ && CE_F) begin
						SH_ROM_CAP <= 0;
						SH_ROM_WAIT <= 0;"""),
])
