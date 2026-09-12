#!/usr/bin/env python3
"""Who writes 0xFF over Doom CD32X Fusion's CD file buffer, and at what address? (OPEN #1)

WHY
The old model - "the frame-buffer word at SH-2 0x24000200 is never written" - is dead. A live DDR3
trace of a failing boot (tools/mister/boottrace.py) shows the word written with CD data, cleared to
zero, and then actively overwritten with ones, with no CD read command in between. tools/mister/
fbdump.py then maps the damage exactly:

    0x00000-0x001FF  the 32X line table, where it belongs
    0x00200-0x00FFF  0xFF                      3584 bytes
    0x01000-0x011FF  a COPY of the line table    512 bytes
    0x01200-0x01FFF  0xFF                      3584 bytes
    ... repeating on a 4096-byte period, twelve times, to 0x0BE4F
    0x0BE58-0x1FFFF  0x00

and a WORKING boot has the line table only at 0x0000 and no 0xFF anywhere, so both halves of that
pattern are the fault. Two things need naming: which agent writes the ones, and what address the
line-table write is using when its data lands at 0x1000, 0x2000, 0x3000...

This probe answers both without changing behaviour. DBG_FB (VDP.sv, phase49/51's word, whose question
is settled) is repurposed; it lands in telemetry beat 12 low half (0x30200060). Run it together with
tools/phase53_fm_probe.py, which takes the high half, and one build answers the ownership question
too.

    [31:16] A[16:1] of the FIRST frame-buffer write whose data is 0xFFFF
    [15: 8] count of frame-buffer writes with data 0xFFFF (saturating)
    [ 7: 4] count of writes landing in word range 0x800-0x8FF, i.e. byte 0x1000-0x11FF, the first
            aliased line-table block (saturating 15)
    [ 3]    the draw bank the first 0xFFFF write went to
    [ 2]    set if that first 0xFFFF write was a byte write rather than a word write
    [ 1]    FBCR.FS      [0] FS

The originator (MD versus SH-2) is NOT carried here: VDP.sv cannot see it, the FIFO entry would have
to widen to 37 bits, and phase53's refusal counters already separate the two by which side is being
turned away. Add it only if phase53 comes back empty.

Usage: phase55_fbwrite_probe.py <core dir>"""
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
    ("""	bit  [7:0] DBG_WR_N_, DBG_RD_N_;
	bit        DBG_FS_WR, DBG_FS_RD;
	always @(posedge CLK or negedge RST_N) begin
		if (!RST_N) begin
			DBG_WR_N_ <= '0; DBG_RD_N_ <= '0; DBG_FS_WR <= 0; DBG_FS_RD <= 0;
		end
		else begin
			// the queued write, taken as it is handed to the DDR3 port
			if (FB_WR && FIFO_FB_A == 17'h00100) begin
				DBG_FS_WR <= FS;
				if (~&DBG_WR_N_) DBG_WR_N_ <= DBG_WR_N_ + 8'd1;
			end
			// the SH-2 read of the same word
			if (!RD_N && !DRAM_CS_N && A[17:1] == 17'h00100) begin
				DBG_FS_RD <= FS;
				if (~&DBG_RD_N_) DBG_RD_N_ <= DBG_RD_N_ + 8'd1;
			end
		end
	end
	assign DBG_FB = {DBG_WR_N_, DBG_RD_N_, 8'h00, DBG_FS_WR, DBG_FS_RD, MODE, 2'b00, FBCR.FS, FS};""",
     """	// Catch the agent that fills the CD file buffer with ones (tools/phase55_fbwrite_probe.py).
	// Taken where the FIFO entry is handed to the DDR3 port, so it is the address and data that
	// actually commit, not what was asked for.
	bit [15:0] DBG_FF_A;
	bit  [7:0] DBG_FF_N;
	bit  [3:0] DBG_ALIAS_N;
	bit        DBG_FF_FB, DBG_FF_BYTE, DBG_FF_SEEN;
	always @(posedge CLK or negedge RST_N) begin
		if (!RST_N) begin
			DBG_FF_A <= '0; DBG_FF_N <= '0; DBG_ALIAS_N <= '0;
			DBG_FF_FB <= 0; DBG_FF_BYTE <= 0; DBG_FF_SEEN <= 0;
		end
		else if (FB_WR) begin
			if (FIFO_FB_D == 16'hFFFF && FIFO_FB_WE == 2'b11) begin
				if (!DBG_FF_SEEN) begin
					DBG_FF_SEEN <= 1;
					DBG_FF_A    <= FIFO_FB_A[16:1];
					DBG_FF_FB   <= FIFO_FB_FB;
					DBG_FF_BYTE <= 0;
				end
				if (~&DBG_FF_N) DBG_FF_N <= DBG_FF_N + 8'd1;
			end
			else if ((FIFO_FB_D[15:8] == 8'hFF || FIFO_FB_D[7:0] == 8'hFF) && FIFO_FB_WE != 2'b11) begin
				if (!DBG_FF_SEEN) begin
					DBG_FF_SEEN <= 1;
					DBG_FF_A    <= FIFO_FB_A[16:1];
					DBG_FF_FB   <= FIFO_FB_FB;
					DBG_FF_BYTE <= 1;
				end
				if (~&DBG_FF_N) DBG_FF_N <= DBG_FF_N + 8'd1;
			end
			// writes into the first aliased line-table block: word 0x800-0x8FF = byte 0x1000-0x11FF
			if (FIFO_FB_A[16:1] >= 16'h0800 && FIFO_FB_A[16:1] <= 16'h08FF && ~&DBG_ALIAS_N)
				DBG_ALIAS_N <= DBG_ALIAS_N + 4'd1;
		end
	end
	assign DBG_FB = {DBG_FF_A, DBG_FF_N, DBG_ALIAS_N, DBG_FF_FB, DBG_FF_BYTE, FBCR.FS, FS};"""),
])
