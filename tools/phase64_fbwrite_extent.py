#!/usr/bin/env python3
"""Count frame-buffer writes per displayed frame, and their address extent.

Night Trap's picture is narrow IN THE BUFFER: the displayed buffer's line 100 holds data to only
~224-242 of 320 pixels and the rest of every line reads zero, while the line table is a correct ramp
with a 320-pixel stride. So the 32X VDP is innocent and something writes short lines.

A full 320x224 8bpp frame is 224*160 = 35,840 word writes. This counts writes between frame-select
flips, so the number says directly whether the write loop is short or is landing at wrong addresses:

    ~35,840  full width, look at addresses instead
    ~25,000  about 70% - matches what is in the buffer, so the source or the loop is narrow

DBG_FB (VDP.sv) is repurposed:
    [31:16] writes during the last complete FS period, saturating
    [15: 8] max A[16:9] seen        [7:0] min A[16:9] seen

Usage: phase64_fbwrite_extent.py <core dir>"""
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

edit("rtl/S32X/VDP.sv", [
    ("""	bit [15:0] DBG_FF_A;
	bit  [7:0] DBG_FF_N;
	bit  [3:0] DBG_ALIAS_N;
	bit        DBG_FF_FB, DBG_FF_BYTE, DBG_FF_SEEN;""",
     """	bit [15:0] DBG_FF_A;
	bit  [7:0] DBG_FF_N;
	bit  [3:0] DBG_ALIAS_N;
	bit        DBG_FF_FB, DBG_FF_BYTE, DBG_FF_SEEN;
	// phase64: how many words actually reach the frame buffer in one displayed frame
	bit [15:0] DBG_WPF, DBG_WCNT;
	bit  [7:0] DBG_AMIN, DBG_AMAX;
	bit        DBG_FS_Q;"""),
])

# the probe body: append a second always block just before the DBG_FB assign
p = os.path.join(d, "rtl/S32X/VDP.sv")
s = open(p, encoding="utf-8", errors="replace").read()
anchor = "\tassign DBG_FB = {DBG_FF_A, DBG_FF_N, DBG_ALIAS_N, DBG_FF_FB, DBG_FF_BYTE, FBCR.FS, FS};"
assert s.count(anchor) == 1
body = """	always @(posedge CLK or negedge RST_N) begin
		if (!RST_N) begin
			DBG_WPF <= '0; DBG_WCNT <= '0; DBG_AMIN <= 8'hFF; DBG_AMAX <= '0; DBG_FS_Q <= 0;
		end
		else begin
			DBG_FS_Q <= FS;
			if (FS != DBG_FS_Q) begin           // frame flipped: latch and restart
				DBG_WPF  <= DBG_WCNT;
				DBG_WCNT <= '0;
			end
			else if (FB_WR && ~&DBG_WCNT) DBG_WCNT <= DBG_WCNT + 16'd1;
			if (FB_WR) begin
				if (FIFO_FB_A[16:9] < DBG_AMIN) DBG_AMIN <= FIFO_FB_A[16:9];
				if (FIFO_FB_A[16:9] > DBG_AMAX) DBG_AMAX <= FIFO_FB_A[16:9];
			end
		end
	end
	assign DBG_FB = {DBG_WPF, DBG_AMAX, DBG_AMIN};	// phase64
	wire unused_ff = |{DBG_FF_A, DBG_FF_N, DBG_ALIAS_N, DBG_FF_FB, DBG_FF_BYTE};
"""
s = s.replace(anchor, body, 1)
open(p, "w", encoding="utf-8", newline="").write(s)
print("rtl/S32X/VDP.sv body ok")
