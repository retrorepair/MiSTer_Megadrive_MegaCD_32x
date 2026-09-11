#!/usr/bin/env python3
"""Make the SH-2 cartridge read wait for the SDRAM to ACKNOWLEDGE, as the Mega Drive read already does.

WHY
The cartridge arbiter serves both CPUs, but only one of them checks that its request was accepted:

    IF.sv:908  RS_MD_WAIT: if (ROM_WAIT_SYNC)                            <- waits for busy to RISE
    IF.sv:866  RS_SH_WAIT: if (/*(ROM_WAIT_SYNC || !USE_ROM_WAIT) &&*/ CE_F)   <- ACK COMMENTED OUT

So the SH-2 path advances to RS_SH_READ on a fixed timer - two CE_F periods, 4 to 5 clk_sys
(74.5-93 ns) after raising the strobes - having never confirmed the SDRAM took the request.

sdram.sv only accepts a request at a clk_ram edge where state == STATE_IDLE, and it tests refresh
BEFORE port 0 in the same else-if chain (sdram.sv:161-167). With prg_first set it also steps over
port 0 outright whenever Mega CD PRG-RAM has a pending edge (sdram.sv:167). Cartridge-only, ports
1 (CD BIOS), 2 (PRG-RAM) and 3 (PCM) are idle, the controller is in STATE_IDLE when the strobe
arrives, and acceptance happens within ~1 clk_ram - inside the timer, so the fixed delay works by
luck. With the Mega CD running those ports keep the controller busy, a refresh lands in the gap,
and acceptance slips to 8-14 clk_ram - PAST the timer.

When that happens RS_SH_READ is entered with ROM_WAIT still LOW, so the capture at IF.sv:878 fires
on a request that has not started yet and takes the PREVIOUS port-0 transaction's word, and
SH_ROM_CAP then locks that stale value in so the real data - which arrives a cycle or two later -
is discarded. The SH-2 is released with a wrong word.

Measured: the master reads a function pointer from a PC-relative longword literal and jumps through
it, with the ROM's true contents read straight out of the game file:

    0201DC34 mov.l 0x201dce8,r14   ROM holds 0201F284   master got 00000001
    0201C57C mov.l 0x201c5b0,r5    ROM holds 02017E38   master got 00000012
    0201DC5C mov.l 0x201dcfc,r2    ROM holds 0201F6EC   master got 00002E01

and the correlation is exactly as predicted: with the disc in, the fault fires; cartridge-only
Fusion, 4 consecutive runs, zero faults; plain Doom 32X cartridge-only, none.

THE FIX
Restore the acknowledgement qualifier that was commented out, so the SH-2 waits for ROM_WAIT to
rise before believing the bus - identical in shape to RS_MD_WAIT, which has always done this.

The `!CART_EXT` escape is carried over from the RS_MD_WAIT deadlock fix (r11) and is NOT optional
padding: if nothing behind the connector answers the cycle, ROM_WAIT can never rise and waiting on
it hangs both SH-2s for ever. cart.sv ties the ROM write strobes off for a normal cartridge, so an
SH-2 WRITE into cartridge space produces no SDRAM request at all - precisely the case that wedged
the MD path. CART_EXT means "the cartridge really is fetching or storing for this cycle, so
ROM_WAIT will rise".

Usage: phase43_sh_rom_handshake.py <core dir>"""
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
    ("""				RS_SH_WAIT: begin
					if (/*(ROM_WAIT_SYNC || !USE_ROM_WAIT) &&*/ CE_F) begin
						ROM_ST <= RS_SH_READ;
					end
				end""",
     """				RS_SH_WAIT: begin
						// Wait for the SDRAM to ACKNOWLEDGE the request before believing the bus. This
						// qualifier was commented out, so this path advanced on a fixed CE_F timer - about
						// 75-93 ns - without ever checking the request had been accepted. RS_MD_WAIT below
						// has always waited for ROM_WAIT_SYNC; the asymmetry was the bug.
						//
						// It worked cartridge-only because sdram.sv is idle when the strobe arrives and
						// takes the request within a clk_ram. With the Mega CD running, its BIOS ROM,
						// PRG-RAM and PCM ports keep the controller busy and refresh is tested BEFORE
						// port 0 (sdram.sv:161-167), so acceptance slips past the timer. RS_SH_READ was
						// then entered with ROM_WAIT still low, captured the PREVIOUS port-0 word, and
						// SH_ROM_CAP locked that stale value in - handing the SH-2 a wrong instruction or
						// literal. That is the wild jump that has been crashing Doom CD32X Fusion.
					if (ROM_WAIT_SYNC && CE_F) begin
						ROM_ST <= RS_SH_READ;
					end else if (!CART_EXT && CE_F) begin
						// Nothing behind the connector answers this cycle, so ROM_WAIT can never rise and
						// waiting on it would hang both SH-2s. Same escape as the RS_MD_WAIT deadlock fix:
						// cart.sv ties the ROM write strobes off for a normal cartridge, so an SH-2 write
						// into cartridge space makes no SDRAM request at all.
						ROM_ST <= RS_SH_READ;
					end
				end"""),
])
