#!/usr/bin/env python3
"""Carry the frame-buffer select through the VDP's write FIFO.

WHY
A frame-buffer write is queued with its address, byte enables and data - but NOT the buffer it was
meant for:

    VDP.sv:198  FIFO_D <= {A[17:1],~UWR_N,~LWR_N,DI};   // 35 bits
    VDP.sv:517  assign FBD_FB = ~FS;                     // sampled when the entry DRAINS

The drain happens several clocks later (the FIFO is 8 deep and each entry is held for a few cycles),
so any write still in flight when FS flips is committed to the buffer selected AFTER the flip. The
SH-2 asked for one buffer and the data lands in the other.

This is a real defect independent of any particular title: it silently misdirects up to 8 writes at
every frame-buffer flip, for ever, in every 32X game.

It is NOT, however, the cause of Doom CD32X Fusion's ~50% boot failure, and this commit does not
claim to fix that. That failure was measured to have FS@write == FS@read on every failing boot (see
HANDOFF.md), and it misdirects whole regions rather than 8 words. Kept separate deliberately.

THE FIX
Capture the draw bank into the FIFO entry at QUEUE time and use the queued value when the entry is
written out. Reads and the auto-fill engine keep using the live ~FS: both are generated in real
time and are not queued, so the current bank is correct for them.

    assign FBD_FB = (!FILL_EXEC && FB_WR) ? FIFO_FB_FB : ~FS;

FB_WR and FB_RD never overlap - the read path is gated on !FIFO_FB_WRITE && FIFO_EMPTY (VDP.sv:183)
- so the mux cannot steal the bank from a read in progress.

VDPFIFO widens 35 -> 36 bits (32X_mem.sv, an scfifo megafunction: port widths plus lpm_width). It is
an 8-word MLAB, so one more bit costs nothing.

Usage: phase52_fifo_carries_fb.py <core dir>"""
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


edit("rtl/S32X/32X_mem.sv", [
    ("""	input	  CLK;
	input	[34:0]  DATA;
	input	  RDREQ;
	input	  WRREQ;
	output	  EMPTY;
	output	  FULL;
	output	[34:0]  Q;

	wire  sub_wire0;
	wire  sub_wire1;
	wire [34:0] sub_wire2;
	wire  EMPTY = sub_wire0;
	wire  FULL = sub_wire1;
	wire [34:0] Q = sub_wire2[34:0];""",
     """	// 36 bits, not 35: the extra bit carries the frame-buffer select with each queued write
	// (tools/phase52_fifo_carries_fb.py). An 8-word MLAB, so the width costs nothing.
	input	  CLK;
	input	[35:0]  DATA;
	input	  RDREQ;
	input	  WRREQ;
	output	  EMPTY;
	output	  FULL;
	output	[35:0]  Q;

	wire  sub_wire0;
	wire  sub_wire1;
	wire [35:0] sub_wire2;
	wire  EMPTY = sub_wire0;
	wire  FULL = sub_wire1;
	wire [35:0] Q = sub_wire2[35:0];"""),
    ("""		scfifo_component.intended_device_family = "Cyclone V",
		scfifo_component.lpm_hint = "RAM_BLOCK_TYPE=MLAB",
		scfifo_component.lpm_numwords = 8,
		scfifo_component.lpm_showahead = "ON",
		scfifo_component.lpm_type = "scfifo",
		scfifo_component.lpm_width = 35,""",
     """		scfifo_component.intended_device_family = "Cyclone V",
		scfifo_component.lpm_hint = "RAM_BLOCK_TYPE=MLAB",
		scfifo_component.lpm_numwords = 8,
		scfifo_component.lpm_showahead = "ON",
		scfifo_component.lpm_type = "scfifo",
		scfifo_component.lpm_width = 36,"""),
])

edit("rtl/S32X/VDP.sv", [
    ("""	bit [34:0] FIFO_D;
	bit [34:0] FIFO_Q;""",
     """	bit [35:0] FIFO_D;
	bit [35:0] FIFO_Q;"""),
    ("""	bit [17:1] FIFO_FB_A;""",
     """	bit        FIFO_FB_FB;		// the draw bank this entry was queued for (phase52)
	bit [17:1] FIFO_FB_A;"""),
    ("""					FIFO_D <= {A[17:1],~UWR_N,~LWR_N,DI};""",
     """					// capture the draw bank WITH the write: FS can flip before this entry drains
					FIFO_D <= {~FS,A[17:1],~UWR_N,~LWR_N,DI};"""),
    ("""			FIFO_FB_A <= '0;""",
     """			FIFO_FB_FB <= 0;
			FIFO_FB_A <= '0;"""),
    ("""				{FIFO_FB_A,FIFO_FB_WE,FIFO_FB_D} <= FIFO_Q;""",
     """				{FIFO_FB_FB,FIFO_FB_A,FIFO_FB_WE,FIFO_FB_D} <= FIFO_Q;"""),
    ("""	// the drawn buffer is the one not displayed: FS=1 displays buffer 1 and draws buffer 0
	assign FBD_FB = ~FS;""",
     """	// The drawn buffer is the one not displayed: FS=1 displays buffer 1 and draws buffer 0.
	// A QUEUED write uses the bank it was queued for, not whatever is current when it drains
	// (tools/phase52_fifo_carries_fb.py) - otherwise a flip mid-FIFO sends it to the wrong buffer.
	// Reads and the auto-fill engine are generated in real time and correctly use the live bank;
	// FB_WR and FB_RD never overlap because the read path is gated on !FIFO_FB_WRITE && FIFO_EMPTY.
	assign FBD_FB = (!FILL_EXEC && FB_WR) ? FIFO_FB_FB : ~FS;"""),
])
