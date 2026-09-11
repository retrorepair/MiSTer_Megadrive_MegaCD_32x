#!/usr/bin/env python3
"""Latch FS at the exact write and the exact read of the frame-buffer word the game reads back.

WHY
Doom CD32X Fusion fails to reach its menu on 33-58% of boots. The chain is established:

    numtextures = LITTLELONG(*(int*)0x24000200)   (r_data.c R_InitTextures, I_TempBuffer)
    reads 0xFFFFFFFF -> numtextures = (short)-1 -> memset(ptr,0,-20) never terminates
    -> all 256 KB of work RAM zeroed, slave code destroyed, black screen

and the buffer contents discriminate perfectly over 10 boots:
    BLACK: FB0 = FFFFFFFF (88% never written), FB1 = 00000000
    MENU : FB0 = 00000000,                     FB1 = 00000000

So the read-back came from a different buffer than the write. FBD_FB = ~FS, and FS == FBCR.FS on
every boot (good and bad) with MODE == 1, so this is NOT a latch or polarity fault.

TWO MODELS WERE TESTED AND ONE IS DEAD:
  - "the 127.5 KB clear is slow enough to be cut by a flip": tools/phase50 made the clear 2.3x
    faster (FIFO_FB_WAIT 5 -> 1) and the failure rate did NOT move (5/12 vs 8/12). Duration is not
    the driver. REVERTED.
  - remaining: the flip lands in the GAP between the clear and the read-back, which is independent
    of clear speed.

Rather than guess again, latch FS at the two accesses that actually matter: the write of
frame-buffer word 0x100 (byte offset 0x200) and the read of the same word. If they differ on a
failing boot the bank mismatch is proven at the exact access, and the fix can target when FS is
allowed to move.

Beat 12 (0x30200060) = {ms_from3, DBG_FB}, DBG_FB now:
    [31:24] writes seen to word 0x100      [23:16] reads seen of word 0x100
    [7]     FS at the last such write      [6]     FS at the last such read
    [5:4]   MODE     [1] FBCR.FS           [0] FS (current)

Usage: phase51_fs_at_access.py <core dir>"""
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
    ("""	bit [15:0] DBG_FS_TOG;
	bit        DBG_FS_D;
	always @(posedge CLK or negedge RST_N) begin
		if (!RST_N) begin DBG_FS_TOG <= '0; DBG_FS_D <= 0; end
		else begin
			DBG_FS_D <= FS;
			if (FS != DBG_FS_D) DBG_FS_TOG <= DBG_FS_TOG + 16'd1;
		end
	end
	assign DBG_FB = {DBG_FS_TOG, 10'h000, MODE, 2'b00, FBCR.FS, FS};""",
     """	// FS at the exact accesses that decide the failure: the write of frame-buffer word 0x100
	// (SH-2 byte offset 0x200) and the read-back of the same word, which is where the game gets
	// numtextures. If these disagree on a failing boot, the bank mismatch is proven at the access.
	bit  [7:0] DBG_WR_N_, DBG_RD_N_;
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
	assign DBG_FB = {DBG_WR_N_, DBG_RD_N_, 8'h00, DBG_FS_WR, DBG_FS_RD, MODE, 2'b00, FBCR.FS, FS};"""),
])
