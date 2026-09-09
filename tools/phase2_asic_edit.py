#!/usr/bin/env python3
"""Sub-CPU PRG-RAM acknowledge timing back to the pristine srg320 scheme.
The NukedMD-MegaCD project acknowledged PRG-RAM reads as soon as the SDRAM accepted the request and posted
writes, tuned to the gate-level 68000's data-latch timing (one 80 ns clock after DTACK). This core's sub-CPU
is fx68k, which latches on its own enable phase; with the early acknowledge it can latch before the SDRAM
data is back. Symptom on hardware: corrupt BIOS logo graphics (decompressed by the sub-CPU into Word RAM).
Restored: DTACK when the read data is back / when the write has been issued. Everything else in the NukedMD
ASIC (EDT/DSR latches, INT2 edge acknowledge, CDD frame timer, DMA write-protect, PCM RAM ready) is kept.
Usage: phase2_asic_edit.py <core/rtl/MCD/ASIC.vhd>"""
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8", errors="replace").read()
s = "\n".join(l.rstrip() for l in s.replace("\r\n", "\n").split("\n"))  # normalise CRLF / trailing whitespace

def rep(old, new):
    global s
    assert old in s, "anchor missing: " + old[:70]
    s = s.replace(old, new, 1)

rep("""								PRG_RAM_RD <= S68K_RNW;
								-- Writes are posted: address and data are latched here, so the CPU can be
								-- acknowledged at once (real PRG-RAM takes writes without wait states); the
								-- next PRG-RAM access still waits for this one to reach the SDRAM controller.
								if S68K_RNW = '0' then
									S68K_PRGRAM_DTACK_N <= '0';
								end if;
								PRSS <= PRS_WAIT;""",
"""								PRG_RAM_RD <= S68K_RNW;
								-- (fx68k sub-CPU: writes are acknowledged in PRS_WRITE, reads in PRS_READ, as upstream)
								PRSS <= PRS_WAIT;""")
rep("""							if PRG_RAM_RD = '1' then
								-- The SDRAM controller has accepted the read: from here the data arrives in a fixed
								-- ~60 ns, so DTACK can go now. The 68000 latches data one clock (80 ns) after it
								-- samples DTACK; acknowledging only once the data was back cost the die-accurate
								-- CPU a wait state on nearly every PRG-RAM fetch (measured 93-105 ns AS to DTACK)
								-- where the real PRG-RAM answers with none (mcd-verificator VAR test).
								S68K_PRGRAM_DTACK_N <= '0';
								PRSS <= PRS_READ;""",
"""							if PRG_RAM_RD = '1' then
								PRSS <= PRS_READ;""")
rep("""							S68K_PRGRAM_DO <= PRG_DI;

							PRSS <= PRS_END;""",
"""							S68K_PRGRAM_DO <= PRG_DI;
							S68K_PRGRAM_DTACK_N <= '0';   -- data is back: acknowledge now (fx68k latches on its next enable)
							PRSS <= PRS_END;""")
rep("""						PRG_RAM_WRL <= '0';
						PRG_RAM_WRH <= '0';
						-- No DTACK here: the CPU's write was acknowledged when it was posted (PRS_IDLE). Asserting it
						-- again once the SDRAM has accepted the write, up to ~300 ns later under contention, landed
						-- in the CPU's NEXT bus cycle and terminated it with S68K_PRGRAM_DO (the previous read's
						-- data), whatever its target: random sub-CPU corruption a few times a minute, and the
						-- "0 ns AS->DTACK" minimum seen in the telemetry since build 21.
						PRSS <= PRS_END;""",
"""						PRG_RAM_WRL <= '0';
						PRG_RAM_WRH <= '0';
						S68K_PRGRAM_DTACK_N <= '0';   -- write issued: acknowledge (upstream timing)
						PRSS <= PRS_END;""")
open(p, "w", encoding="utf-8").write(s)
print("asic ok")
