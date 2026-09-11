#!/usr/bin/env python3
"""Latch, in hardware, the caller of the memset that never returns.

WHY
On a black-screen Fusion boot the master SH-2 sits for ever in memset's BYTE tail:

    0201FD18  mov    #12,r0
    0201FD1A  cmp/gt r6,r0        12 > len ?  -> byte path
    0201FD1C  mov    r4,r0
    0201FD1E  bt/s   0x201fd48
    0201FD20  add    r4,r6        r6 = dest + len
    ...
    0201FD4C  mov.b  r5,@r0
    0201FD4E  add    #1,r0
    0201FD50  cmp/eq r6,r0
    0201FD52  bf     0x201fd4c

100% of 20000 PC samples land in 0201FD4C..52 and never in the 8-bytes-at-a-time loop at
0201FD3C, so len < 12; and for the end pointer to be unreachable, len must be NEGATIVE, which
puts r6 below dest and walks r0 away from it through a 32-bit wrap. Work RAM is left entirely
zero - 0 non-zero words in 128 KB - including the slave's code, which is why the slave executes
zeros at 06005FCA.

A negative length is an `end - start` with a corrupt pointer, so this is still a corrupted read -
the same family as the RS_SH_WAIT bug fixed in r30, landing in a data value instead of a code
pointer. That is why r30 does not catch it and neither does r31 (measured: 2/5 and 1/5 boots
reach the menu).

Sampling the PC from Linux CANNOT catch the transition: the telemetry beat updates far slower
than the SH-2, and a Python poller reported "booted fine" eight times while the screen was black
and the master was demonstrably inside memset. So latch it in hardware.

HOW
Keep a three-deep trail of distinct PCs while OUTSIDE memset, count clk_sys spent continuously
INSIDE it, and freeze the trail when that count saturates. 24 bits at 53.693 MHz is 0.31 s;
the largest legitimate memset here (Z_Init's 0x33000 zone) takes about 6 ms through the long
loop, so the threshold cannot fire on a normal call.

Beat 8  (0x30200040): {caller_1, caller_2}   most recent distinct PCs before entering memset
Beat 12 (0x30200060): {caller_3, 0}

Usage: phase45_memset_caller.py <core dir>"""
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


# find the jump-trail block installed by phase41 and swap its trigger
edit("MegaCD.sv", [
    ("""wire [63:0] tel_trap = {jump_from, jump_to};""",
     """wire [63:0] tel_trap = {ms_from1, ms_from2};

// Catch the caller of the memset that never returns (tools/phase45_memset_caller.py). Trail the
// last distinct PCs while OUTSIDE memset, count clk_sys spent continuously INSIDE it, and freeze
// when that saturates: 24 bits is 0.31 s, where the largest legitimate memset here is about 6 ms.
reg [31:0] ms_d, ms_1, ms_2, ms_3;
reg [31:0] ms_from1, ms_from2, ms_from3;
reg [23:0] ms_cnt;
reg        ms_hit;
wire       ms_in = (S32X_MSH_PC >= 32'h0201FD18) && (S32X_MSH_PC <= 32'h0201FD56);
always @(posedge clk_sys) begin
	if (reset) begin
		ms_d <= 0; ms_1 <= 0; ms_2 <= 0; ms_3 <= 0;
		ms_from1 <= 0; ms_from2 <= 0; ms_from3 <= 0;
		ms_cnt <= 0; ms_hit <= 0;
	end
	else if (!ms_hit) begin
		if (S32X_MSH_PC != ms_d) begin
			ms_d <= S32X_MSH_PC;
			if (!ms_in) begin
				ms_3 <= ms_2;
				ms_2 <= ms_1;
				ms_1 <= ms_d;
			end
		end
		if (ms_in) begin
			ms_cnt <= ms_cnt + 24'd1;
			if (&ms_cnt) begin
				ms_hit   <= 1;
				ms_from1 <= ms_1;
				ms_from2 <= ms_2;
				ms_from3 <= ms_3;
			end
		end
		else ms_cnt <= 24'd0;
	end
end"""),
    ("""wire [63:0] tel_int = {pc_ctx1, pc_ctx2};""",
     """wire [63:0] tel_int = {ms_from3, 32'h00000000};
wire unused_jt = |{jump_from, jump_to, pc_ctx1, pc_ctx2};"""),
])
