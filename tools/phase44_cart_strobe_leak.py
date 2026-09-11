#!/usr/bin/env python3
"""Stop the Mega Drive's raw cartridge strobes reaching the cart while the 32X arbiter is idle.

WHY
sdram.sv starts a transaction on a RISING EDGE only, and holds old_rd while the strobe stays high:

    sdram.sv:155  old_rd <= old_rd & rd;
    sdram.sv:167  else if (((~old_rd[0] && rd[0]) || (~old_wr[0] && wr[0])) ...

but the cartridge strobe muxes are qualified by `&& S32X_CE0`, so whenever the arbiter is BETWEEN
grants the 68000's raw /CE0 and /CAS0 fall straight through to the cartridge, carrying the MD's
address (S32X_CA follows SH_ROM_GRANT, 32X.sv:359):

    IF.sv:1103  assign CCE0_N  = ADCR.ADEN && !DCR.RV && S32X_CE0 ? ~S32X_CE0  : MD_BIOS_SEL | CE0_N_SYNC[0];
    IF.sv:1107  assign CCAS0_N = ADCR.ADEN && !DCR.RV && S32X_CE0 ? ~S32X_CAS0 : CAS0_N_SYNC[0];
    cart.sv:231 wire ROM_ACCESS = ~CE0_N | ROM_LIN_EN;
    cart.sv:243 assign ROM_RD   = ROM_ACCESS & ~CAS0_N;

So an unarbitrated MD read can raise rd0. If the controller accepts it, rd0 is ALREADY HIGH when the
arbiter then grants the SH-2: the SH-2's own request produces no rising edge and is never issued -
only the address underneath it changes. The SH-2 waits on the MD's busy, sees it fall, and captures
the MD 68000's word read from the MD's address. It looks like real cartridge data, which makes it
far nastier than obvious garbage, and the MD's own arbitrated cycle re-reads the address afterwards
so nothing looks wrong on the MD side.

This is NOT the bug phase43 fixed. phase43 made the SH-2 wait for ROM_WAIT to rise; here ROM_WAIT
DOES rise - for the wrong access. It scales with how busy the 68000 is.

THE FIX
When the 32X adapter owns the cartridge bus (ADCR.ADEN && !DCR.RV), drive the ROM strobes from the
arbiter ONLY. Between grants they are then deasserted, rd0 falls, and every arbitrated access gets a
clean rising edge. MD cartridge cycles still reach the cart: they set MD_ROM_WAIT (IF.sv:836) and are
served by RS_MD_RW, which reproduces the MD's own strobe values (S32X_CAS0 <= ~CAS0_V).

SCOPE - deliberately only CCE0_N and CCAS0_N. CASEL_N, CLWR_N and CUWR_N keep their `&& S32X_CE0`
qualifier, because the arbiter never grants for register cycles like $A130F1 (MD_ROM_WAIT requires
MD_32XROM_SEL or !CE0_N) and deasserting those while idle would break SRAM banking. ROM_RD depends
only on CE0_N and CAS0_N, so these two are sufficient.

The `!CART_EXT` escapes in RS_SH_WAIT and RS_MD_WAIT are unaffected: both are evaluated AFTER the
grant, when S32X_CE0 is 1 and the muxes take the arbiter branch either way.

With ADEN off, or DCR.RV set (the MD has direct ROM access), the raw pass-through is unchanged -
there is no SH-2 cartridge access to collide with in either case (RS_IDLE gates on !DCR.RV).

Usage: phase44_cart_strobe_leak.py <core dir>"""
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
    ("""	assign CCE0_N  = ADCR.ADEN && !DCR.RV && S32X_CE0 ? ~S32X_CE0 : MD_BIOS_SEL | CE0_N_SYNC[0];
	assign CCAS0_N = ADCR.ADEN && !DCR.RV && S32X_CE0 ? ~S32X_CAS0 : CAS0_N_SYNC[0];""",
     """	// The `&& S32X_CE0` qualifier is deliberately ABSENT from these two (tools/phase44_cart_strobe_leak.py).
	// With it, the 68000's raw /CE0 and /CAS0 reached the cartridge whenever the arbiter was between
	// grants, and cart.sv turns those into ROM_RD -> the SDRAM's port-0 read strobe. sdram.sv starts a
	// transaction on a RISING EDGE only and holds old_rd while the strobe stays high, so an
	// unarbitrated MD read left rd0 already high when the SH-2 was granted: the SH-2's request never
	// produced an edge, was never issued, and it captured the 68000's word from the 68000's address.
	// Driving them from the arbiter alone means rd0 falls between grants and every access gets a clean
	// edge. MD cartridge cycles still reach the cart through RS_MD_RW, which reproduces the MD's own
	// strobes. CASEL_N/CLWR_N/CUWR_N below KEEP the qualifier: the arbiter never grants for register
	// cycles such as $A130F1, and gating those would break SRAM banking.
	assign CCE0_N  = ADCR.ADEN && !DCR.RV ? ~S32X_CE0 : MD_BIOS_SEL | CE0_N_SYNC[0];
	assign CCAS0_N = ADCR.ADEN && !DCR.RV ? ~S32X_CAS0 : CAS0_N_SYNC[0];"""),
])
