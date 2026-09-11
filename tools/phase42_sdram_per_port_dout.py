#!/usr/bin/env python3
"""Give each SDRAM port its own output register, WITHOUT touching the SDRAM_DQ capture path.

WHY
sdram.sv has a single data register aliased to every port:

    sdram.sv:134  reg [15:0] dout;
    sdram.sv:136  assign dout0 = dout;  ... dout1 ... dout2 ... dout3 ... dout4
    sdram.sv:227  if (state == STATE_READY && ram_req) dout <= SDRAM_DQ;

so a port's data survives only until ANY other port completes a read. Every consumer has had to
race to latch it, and that race is the most expensive bug in this core - found three times now:

  r7   the Mega Drive cartridge read returned a live wire into dout   (tools/phase17_cart_latch.py)
  r21  the SH-2 cartridge read latched on CE_F, up to three clocks late (tools/phase35_sh_rom_latch.py)
  r27  STILL corrupting SH-2 longword literal reads from cart ROM

Measured on Doom CD32X Fusion with the r27 jump trail. The master loads a function pointer with a
PC-relative longword read and jumps through it:

    0201DC34  mov.l 0x201dce8,r14      ROM holds 0201F284 -> master got 00000001
    0201DC40  jsr   @r14
    0201C57C  mov.l 0x201c5b0,r5       ROM holds 02017E38 -> master got 00000012

Values like 1 and 0x12 are what the Mega CD's BIOS ROM (port 1), PRG-RAM (port 2) or PCM (port 3)
was reading at that moment - they landed in the shared register between the SH-2's two 16-bit bus
cycles. The SH-2 caches cart ROM, so one poisoned word persists for the whole 16-byte line. The
master then jumps to a tiny address, walks forward through the BIOS vector table (entries are all
0000013C, harmless as data) and stops in the BRA-to-self trap at 0x13C - the "wild jump into the
vector table" seen since r18, and why it only happens with the Mega CD active.

THE FIX, and why it is in two stages
The obvious form - five enabled registers each capturing SDRAM_DQ directly - was built as r28 and
DOES NOT WORK: the core comes up with both SH-2s dead and no $A151xx traffic at all. SDRAM_DQ is a
tight input path (r25 had already failed timing on sdram|reset[4] -> SDRAM_DQ[0]~en), and fanning it
out to five loads spread across the fabric breaks the capture.

So leave that path exactly as it was - one register, one load, same placement - and split per port
one cycle LATER, from the already-captured value. There is room: busy is ram_req | ram_req_d |
ram_req_d2, so it stays high for three clk_ram cycles after STATE_READY, and consumers sample when
it falls. Distributing on the next cycle still lands two cycles before that.

The r7 and r21 consumer-side latches stay. They are correct, they cost nothing, and removing working
code to prove a point is how regressions happen.

Usage: phase42_sdram_per_port_dout.py <core dir>"""
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


edit("rtl/sdram.sv", [
    ("""reg [15:0] dout;

assign dout0 = dout;
assign dout1 = dout;
assign dout2 = dout;
assign dout3 = dout;
assign dout4 = dout;""",
     """// `dout` stays exactly as it was: ONE register with ONE load on SDRAM_DQ. That input path is
// tight and fanning it out to five enabled registers kills the capture outright (built as r28:
// both SH-2s dead, no $A151xx traffic). The per-port split below happens a cycle later instead.
reg [15:0] dout;

// One register PER PORT (tools/phase42_sdram_per_port_dout.py). Sharing `dout` across all five let
// any port's read overwrite another's data before its consumer sampled it, corrupting 68000 and
// SH-2 instruction fetches whenever the Mega CD was active.
reg [15:0] dout_p0, dout_p1, dout_p2, dout_p3, dout_p4;
reg  [4:0] dout_sel;

assign dout0 = dout_p0;
assign dout1 = dout_p1;
assign dout2 = dout_p2;
assign dout3 = dout_p3;
assign dout4 = dout_p4;"""),
    ("""	if(state == STATE_READY && ram_req) begin
		dout <= SDRAM_DQ;
		active <= 0;
		ram_req <= 0;
	end""",
     """	if(state == STATE_READY && ram_req) begin
		dout <= SDRAM_DQ;
		active <= 0;
		ram_req <= 0;
	end

	// Hand the captured word to the port that asked for it, one cycle after the capture. ram_req is
	// one-hot for the port being served, and busy (ram_req | ram_req_d | ram_req_d2) stays high for
	// three cycles after STATE_READY, so this lands two cycles before any consumer samples.
	dout_sel <= (state == STATE_READY) ? ram_req : 5'd0;
	if (dout_sel[0]) dout_p0 <= dout;
	if (dout_sel[1]) dout_p1 <= dout;
	if (dout_sel[2]) dout_p2 <= dout;
	if (dout_sel[3]) dout_p3 <= dout;
	if (dout_sel[4]) dout_p4 <= dout;"""),
])
