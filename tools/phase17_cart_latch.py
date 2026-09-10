#!/usr/bin/env python3
"""Return the LATCHED cartridge word to the Mega Drive instead of a live wire into shared memory.

THE DEFECT. sdram.sv has ONE data register shared by all five ports:

    reg [15:0] dout;
    assign dout0 = dout; assign dout1 = dout; ... assign dout4 = dout;
    if (state == STATE_READY && ram_req) dout <= SDRAM_DQ;

Every consumer in the design latches that word as soon as its own port handshake completes - the Mega CD
gate array does (ASIC.vhd:809-818), the 32X does for the SH-2 and for its own $880000 window - with ONE
exception. A Mega Drive read of cartridge space $000000-$3FFFFF falls through to `VDO = CDI`, which is a
live combinational wire running sdram dout -> CART_MEM_DO -> cart.sv VDO -> S32X_CDI -> IF VDO ->
GEN_VDI -> MBUS_DI -> the 68000's data input. Nothing holds it.

WHY THAT BREAKS. fx68k re-samples its data input on every enPhi2 until the bus cycle ends and keeps the
LAST one, and the 68000 runs at one clock in seven of clk_sys. So the word must stay valid for roughly
130-200 ns after the 32X released the cycle. One SDRAM access is about 65 ns. In that window the Mega
CD's sub-CPU (port 2) or the PCM engine (port 3) - both asynchronous to the Mega Drive's bus - can
complete an access and overwrite the shared register, and the 68000 latches THEIR word instead. The
capture is not even qualified by read versus write, so a write clobbers it too.

That is why it only bites once the Mega CD sub-CPU is running: mode 1 titles (mcd-verificator, Doom
CD32X Fusion) fail, while Mega Drive and 32X cartridges on their own are fine. A wrong word in an
instruction fetch desynchronises the 68000's prefetch, which is why the verificator ends up executing
two bytes into `lea $F36E,a2` at $D38E and taking a line-F exception.

THE FIX. The 32X's ROM state machine already latches the word at exactly the right instant - RS_MD_READ
does `MD_ROM_DO <= CDI_SYNC` the moment port 0 reports done, for pass-through cycles as well as for its
own window - and asserts DTACK from there. It simply does not return it. Return it, exactly as the line
above already does for $880000-$9FFFFF.

Safe because Mega Drive work RAM, I/O and VDP reads never take this path: gen.sv:458 serves them from
WRAM_Q, IO_DO and VDP_DO, and only falls through to the external bus for everything else.
Usage: phase17_cart_latch.py <core dir>"""
import sys, os
d = sys.argv[1]
p = os.path.join(d, "rtl/S32X/IF.sv")
s = open(p, encoding="utf-8", errors="replace").read()
old = """		else if (MD_VDP_SEL)
			VDO = VDP_DI;
		else
			VDO = CDI;"""
new = """		else if (MD_VDP_SEL)
			VDO = VDP_DI;
		else
			// Cartridge space. Return the word LATCHED by RS_MD_READ, not a live wire into sdram.sv's
			// single shared dout register - the Mega CD sub-CPU (port 2) and the PCM engine (port 3)
			// run asynchronously to this bus cycle and will overwrite it before fx68k takes its final
			// sample. See tools/phase17_cart_latch.py.
			VDO = USE_ROM_WAIT ? MD_ROM_DO : CDI;"""
assert old in s, "anchor missing in IF.sv"
open(p, "w", encoding="utf-8").write(s.replace(old, new, 1))
print("rtl/S32X/IF.sv ok")
