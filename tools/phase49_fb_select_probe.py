#!/usr/bin/env python3
"""Measure the 32X frame-buffer select (FS) around the failure.

WHY
Doom CD32X Fusion reaches its menu on only about half of boots, screen-verified. Measured across 10
boots, the discriminator is PERFECT:

    BLACK: FB0 = FFFFFFFF (88% of a 16 KB sample still 0xFF, i.e. never written), FB1 = 00000000  x5
    MENU : FB0 = 00000000,                                                        FB1 = 00000000  x5

The game reads numtextures as a longword out of the 32X frame buffer at SH-2 0x24000200
(I_TempBuffer = (byte*)framebuffer, r_data.c R_InitTextures). On a failing boot it reads FFFFFFFF,
so numtextures = (short)-1, and

    02020538  mov.w  @r10,r6        ; sign-extended reload of numtextures
    0202053E  muls.w r11,r6         ; len = r11 * numtextures  -> NEGATIVE
    02020546  jsr    @r1            ; memset(ptr, 0, len)

runs for ever, zeroing all 256 KB of work RAM including the slave's code.

So on a failing boot the clear went to FB1 and the read came from FB0. Since FBD_FB = ~FS
(VDP.sv:517), FS must have differed between the clear and the read.

WHAT IS NOT YET KNOWN is why. FS is latched from FBCR.FS at VBLANK, or continuously while the VDP
is blanked:

    VDP.sv:395  if (VBLK || MODE == 2'b0) FS <= FBCR.FS;

If the game double-buffers during the load, FS toggles every frame and a 128 KB clear spanning
several frames would scatter between both buffers. If FS is stable, something else moved it.
Measure before changing anything.

NOTE a separate, genuine defect found while looking, NOT fixed here because it cannot account for a
whole 128 KB clear: the VDP's frame-buffer write FIFO does not carry the buffer select.

    VDP.sv:198  FIFO_D <= {A[17:1],~UWR_N,~LWR_N,DI};   // 35 bits: address, byte enables, data
    VDP.sv:517  assign FBD_FB = ~FS;                     // sampled when the entry DRAINS

so writes queued before a swap are committed to the buffer selected after it. That misdirects at
most the 8 entries in flight. Widening VDPFIFO (a fixed 35-bit megafunction in 32X_mem.sv) is the
fix if it turns out to matter.

Beat 12 (0x30200060) becomes {ms_from3, DBG_FB}, with
    DBG_FB[31:16] = count of FS toggles
    DBG_FB[5:4]   = MODE
    DBG_FB[1]     = FBCR.FS   (what software asked for)
    DBG_FB[0]     = FS        (what the hardware is using)

Usage: phase49_fb_select_probe.py <core dir>"""
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
    ("""	output            FBD_FB,		// buffer being drawn (= ~FS)""",
     """	output     [31:0] DBG_FB,		// tools/phase49_fb_select_probe.py
	output            FBD_FB,		// buffer being drawn (= ~FS)"""),
    ("""	// the drawn buffer is the one not displayed: FS=1 displays buffer 1 and draws buffer 0
	assign FBD_FB = ~FS;""",
     """	// the drawn buffer is the one not displayed: FS=1 displays buffer 1 and draws buffer 0
	assign FBD_FB = ~FS;

	// How often does the draw buffer actually move? (tools/phase49_fb_select_probe.py) A 128 KB
	// I_TempBuffer clear spans several frames, so if FS toggles per frame the clear is scattered
	// across both buffers and the read-back lands in the wrong one.
	bit [15:0] DBG_FS_TOG;
	bit        DBG_FS_D;
	always @(posedge CLK or negedge RST_N) begin
		if (!RST_N) begin DBG_FS_TOG <= '0; DBG_FS_D <= 0; end
		else begin
			DBG_FS_D <= FS;
			if (FS != DBG_FS_D) DBG_FS_TOG <= DBG_FS_TOG + 16'd1;
		end
	end
	assign DBG_FB = {DBG_FS_TOG, 10'h000, MODE, 2'b00, FBCR.FS, FS};"""),
])

edit("rtl/S32X/32X.sv", [
    ("""	output            FBD_FB,""",
     """	output     [31:0] DBG_FB,			// tools/phase49_fb_select_probe.py
	output            FBD_FB,"""),
    ("""		.FBD_FB(FBD_FB),""",
     """		.DBG_FB(DBG_FB),
		.FBD_FB(FBD_FB),"""),
])

edit("MegaCD.sv", [
    ("""	.FBD_FB(S32X_FBD_FB),""",
     """	.DBG_FB(S32X_DBG_FB),
	.FBD_FB(S32X_FBD_FB),"""),
    ("""wire        S32X_FBD_FB, S32X_FBD_RD, S32X_FBD_BUSY, S32X_FBD_RDY;""",
     """wire        S32X_FBD_FB, S32X_FBD_RD, S32X_FBD_BUSY, S32X_FBD_RDY;
wire [31:0] S32X_DBG_FB;		// tools/phase49_fb_select_probe.py"""),
    ("""wire [63:0] tel_int = {ms_from3, ms_from4};""",
     """wire [63:0] tel_int = {ms_from3, S32X_DBG_FB};
wire unused_ms4 = |ms_from4;"""),
])
