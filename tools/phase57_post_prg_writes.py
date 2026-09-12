#!/usr/bin/env python3
"""Post the sub-CPU's PRG-RAM writes, without the unsafe early READ acknowledge.

WHY
The last two mcd-verificator failures are one cause: the sub-CPU is not acknowledged until the SDRAM
has COMPLETED a PRG-RAM write. Real PRG-RAM posts writes - the CPU is acknowledged at once and never
waits. Both failing tests measure sub-CPU response latency and both have writes on the critical path:

  IRQ TEST 0A (@0x018452) - the main CPU writes IFL2 once, waits 6 NOPs, and requires the sub-CPU's
  INT2 handler to have ALREADY written comm status. Before the handler's first instruction runs the
  68000 exception pushes THREE WORDS onto a stack that lives in PRG-RAM.

  CDC FLAGS 41 (@0x014568) - d4/d5 count main<->sub RPC round trips, not poll-loop iterations; each
  round trip is bounded by the sub-CPU's handler writing its reply.

ASIC.vhd already has the posting logic, but it shares OSD bit 28 with an early READ acknowledge that
is NOT safe - it acks when the controller merely accepts the request, and 0.011-0.068% of reads
(250-1500 words/second) would return stale data. The earlier session measured the pair together, saw
the corruption and rejected both. This splits them: writes post, reads keep waiting for data.

THE SECOND HAZARD, which the shared bit would also have hit
PRS_WRITE acknowledges unconditionally. With a posted write the CPU has often already ended its bus
cycle and the strobe-follow logic has released /DTACK, so that second acknowledge lands in the CPU's
NEXT bus cycle and terminates it early - the "build 21 BIOS corruption" the code's own comment warns
about. PRG_WR_POSTED records that this write was already acknowledged so PRS_WRITE does not repeat it.

Posted writes are the DEFAULT (OSD bit 57, sense inverted); set the bit to get upstream behaviour
back for an A/B without rebuilding.

Usage: phase57_post_prg_writes.py <core dir>"""
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


edit("rtl/MCD/ASIC.vhd", [
    # ---- new port
    ("""		DBG_EARLY_DTACK: in std_logic;""",
     """		DBG_EARLY_DTACK: in std_logic;
		PRG_POST_WR		: in std_logic;		-- post sub-CPU PRG-RAM writes (tools/phase57_post_prg_writes.py)"""),

    # ---- new signal
    ("""	signal PRG_RAM_RD 				: std_logic;""",
     """	signal PRG_RAM_RD 				: std_logic;
	signal PRG_WR_POSTED 			: std_logic;	-- this write was already acknowledged in PRS_IDLE"""),

    # ---- reset
    ("""			PRG_RAM_WRL <= '0';
			PRG_RAM_WRH <= '0';
			PRG_RAM_RD <= '0';
			M68K_PRGRAM_DTACK_N <= '1';""",
     """			PRG_RAM_WRL <= '0';
			PRG_RAM_WRH <= '0';
			PRG_RAM_RD <= '0';
			PRG_WR_POSTED <= '0';
			M68K_PRGRAM_DTACK_N <= '1';"""),

    # ---- post the write at issue, on its own control, and remember that we did
    ("""								-- Writes are posted when DBG_EARLY_DTACK is set: address and data are latched
								-- here, so the CPU can be acknowledged at once (real PRG-RAM takes writes
								-- without wait states); the next PRG-RAM access still waits for this one to
								-- reach the SDRAM controller. Default is upstream: acknowledge in PRS_WRITE.
								if DBG_EARLY_DTACK = '1' and S68K_RNW = '0' then
									S68K_PRGRAM_DTACK_N <= '0';
								end if;""",
     """								-- Writes are POSTED (PRG_POST_WR, default on): address and data are latched
								-- here, so the CPU is acknowledged at once exactly as real PRG-RAM does - it
								-- takes writes without wait states. Nothing can be lost by acknowledging
								-- early: PRSS still runs PRS_WAIT -> PRS_WRITE -> PRS_END holding the address
								-- and data, and PRS_IDLE cannot issue the next access until PRG_RDY.
								-- This is NOT the old DBG_EARLY_DTACK, which also acknowledged READS as soon
								-- as the controller accepted them and handed the sub-CPU stale data on
								-- 0.011-0.068% of reads. That half stays behind bit 28 and stays off.
								if PRG_POST_WR = '1' and S68K_RNW = '0' then
									S68K_PRGRAM_DTACK_N <= '0';
									PRG_WR_POSTED <= '1';
								end if;"""),

    # ---- do not acknowledge twice
    ("""					when PRS_WRITE =>
						PRG_RAM_WRL <= '0';
						PRG_RAM_WRH <= '0';
						S68K_PRGRAM_DTACK_N <= '0';   -- write issued: acknowledge (upstream timing)
						PRSS <= PRS_END;""",
     """					when PRS_WRITE =>
						PRG_RAM_WRL <= '0';
						PRG_RAM_WRH <= '0';
						-- Only acknowledge here if the write was NOT posted. A posted write has usually
						-- ended the CPU's bus cycle already, and the strobe-follow logic above has taken
						-- /DTACK back to '1'; asserting it again now would land in the CPU's NEXT bus cycle
						-- and terminate it early - the build 21 BIOS corruption this file warns about.
						if PRG_WR_POSTED = '0' then
							S68K_PRGRAM_DTACK_N <= '0';   -- write issued: acknowledge (upstream timing)
						end if;
						PRG_WR_POSTED <= '0';
						PRSS <= PRS_END;"""),
])

edit("rtl/MCD/MCD.vhd", [
    ("""		DBG_EARLY_DTACK: in std_logic := '0';""",
     """		DBG_EARLY_DTACK: in std_logic := '0';
		PRG_POST_WR		: in std_logic := '1';"""),
    ("""		DBG_EARLY_DTACK => DBG_EARLY_DTACK,""",
     """		DBG_EARLY_DTACK => DBG_EARLY_DTACK,
		PRG_POST_WR => PRG_POST_WR,"""),
])

edit("MegaCD.sv", [
    ("""	.DBG_EARLY_DTACK(status[28]),   // ungated: the A/B is driven by writing MegaCD.CFG, which cannot reach dbg_menu""",
     """	.DBG_EARLY_DTACK(status[28]),   // ungated: the A/B is driven by writing MegaCD.CFG, which cannot reach dbg_menu
	.PRG_POST_WR(~status[57]),      // posted sub-CPU PRG-RAM writes, DEFAULT ON; set bit 57 for upstream timing"""),
    ("""	"H2O[38],PRG cache hits,On,Off;",""",
     """	"H2O[38],PRG cache hits,On,Off;",
	"H2O[57],MCD PRG posted writes,On,Off;","""),
])
