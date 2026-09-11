#!/usr/bin/env python3
"""Keep the 32X PWM FIFO draining when the L/R output mode is off, as PicoDrive does.

WHY
Doom CD32X Fusion's slave SH-2 sits for ever in a 16-byte loop in its own cart ROM:

    0201E5CE  mov.w  @r8,r2      ; read a 16-bit register
    0201E5D0  cmp/pz r2          ; test bit 15
    0201E5D2  bf     0201E5CE    ; spin while bit 15 SET
    0201E5D6  mov.w  r10,@r8     ; then push a value

Bit 15 of the 32X PWM width registers is FULL (32X_PKG.sv PWR_t), so this is the standard
"wait until the PWM FIFO has room, then push a sample" idiom. In this core that FIFO can stop
draining for ever:

    IF.sv:685   if (PWMCR.LMD || PWMCR.RMD) CYC_CNT_NEXT = CYC_CNT + 12'd1;
                else                        CYC_CNT_NEXT = 12'd0;
    IF.sv:696   if (CYC_CNT_NEXT == CYCR && (PWMCR.LMD || PWMCR.RMD)) begin   ... drain ...

With both output-mode fields clear the whole PWM timebase is held at zero and the drain branch is
unreachable, so after three pushes FULL latches and never clears. Anything spinning on FULL hangs,
and in Fusion that takes the master down with it - it waits on a comm register the slave never
services - so nothing is ever drawn.

PicoDrive - the only emulator that supports CD32X at all - consumes the FIFO purely on elapsed
cycles and never consults the output mode. pico/32x/pwm.c consume_fifo_do():

    if (pwm.cycles == 0 || pwm.doing_fifo)
      return;
    while (sh2_cycles_diff >= pwm.cycles) { ... Pico32x.pwm_p[0]--; ... }

and p32x_pwm_read16() calls consume_fifo() on EVERY PWM register read. The only guard is a non-zero
cycle register.

WHAT THIS CHANGES
1. The PWM timebase runs whenever CYCR is non-zero, regardless of LMD/RMD.
2. The FIFO drains on `CYC_CNT_NEXT == CYCR && |CYCR`, matching PicoDrive's sole guard.
3. The audible output stays gated on LMD/RMD, so a title with output disabled still hears nothing -
   only the FIFO bookkeeping changes. Without this the DAC would be fed while output is off.

This is upstream srg320 behaviour too (32X/IF.sv is byte-identical here), so it is a divergence from
the reference emulator rather than a merge error, and worth reporting upstream.

Usage: phase28_pwm_drain.py <core dir>"""
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
    # 1 + 2: run the timebase and drain on the cycle register alone
    ("""			//PWM
			if (PWMCR.LMD || PWMCR.RMD) begin
				CYC_CNT_NEXT = CYC_CNT + 12'd1;
				TIME_CNT_NEXT = TIME_CNT + 4'd1;
			end else begin
				CYC_CNT_NEXT = 12'd0;
				TIME_CNT <= 4'd0;
			end""",
     """			//PWM
			// The FIFO must keep draining even with the L/R output mode off, or a title that queues
			// samples before enabling output leaves FULL latched and any SH-2 spinning on it hangs -
			// which is exactly where Doom CD32X Fusion's slave sits. PicoDrive (pico/32x/pwm.c,
			// consume_fifo_do) advances the FIFO on elapsed cycles alone and its only guard is a
			// non-zero cycle register; the output mode is never consulted. Audibility is handled
			// separately at the DAC below, so nothing is heard while output is disabled.
			if (|CYCR) begin
				CYC_CNT_NEXT = CYC_CNT + 12'd1;
				TIME_CNT_NEXT = TIME_CNT + 4'd1;
			end else begin
				CYC_CNT_NEXT = 12'd0;
				TIME_CNT <= 4'd0;
			end"""),
    ("""				if (CYC_CNT_NEXT == CYCR && (PWMCR.LMD || PWMCR.RMD)) begin""",
     """				if (CYC_CNT_NEXT == CYCR && |CYCR) begin"""),
    # 3: keep silence when the output mode is off
    ("""			if (PWM_OUT) begin
			if (!CYCR[11]) begin""",
     """			if (PWM_OUT) begin
			if (!(PWMCR.LMD || PWMCR.RMD)) begin
				// output disabled: the FIFO still drains (above), but nothing reaches the DAC
				PWM_L <= '0;
				PWM_R <= '0;
			end else if (!CYCR[11]) begin"""),
])
