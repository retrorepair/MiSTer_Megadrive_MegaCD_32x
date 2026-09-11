#!/usr/bin/env python3
"""Expose where the MD 68000 is and whether it is touching COMM0 at all.

WHY
Fusion's master SH-2 posts command 0x2E in COMM0 ($A15120 / SH-2 $20004020) and spins waiting for it
to clear. Measured on r14, CP0R sits at 0x2E00 indefinitely while the 68000 runs at ~27k $A151xx
accesses/s. d32xr's main_loop_handle_req reads $A15120, dispatches through prireqtbl, and ends every
handler with `move.w #0,0xA15120`. So either the 68000 never reaches that read, or the handler for
0x2E blocks - and the 68000 is the one CPU whose position is still unmeasured.

Sampling the MD address bus localises it the same way the SH-2 PC tap localised both SH-2s: the
68000's instruction fetches dominate, so a tight loop shows up as a tight address cluster that can be
disassembled straight out of the ROM with tools/dis68k.py.

Counting reads and writes of $A15120 specifically is the decisive part:
  cp0_rd climbing, cp0_wr flat  -> the 68000 SEES the request and never clears it: its handler for
                                   command 0x2E is blocked (scd_flush_cmd_queue and the $A1200F
                                   polls in src-md/scd.c have no timeout)
  cp0_rd flat                   -> it never reaches main_loop_handle_req at all; the block is
                                   earlier in main_loop
  both climbing                 -> it is servicing and re-posting, and the hang is elsewhere

Beat 7 at DDR3 0x30200038:
       [63:40] last MD bus address (A23:A1 << 1)
       [39:32] last $A151xx register offset touched
       [31:16] MD reads of $A15120
       [15: 0] MD writes to $A15120

Usage: phase29_md_addr.py <core dir>"""
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


edit("MegaCD.sv", [
    ("""wire [63:0] tel_comm = S32X_COMM;""",
     """wire [63:0] tel_comm = S32X_COMM;

// Where the MD 68000 actually is, and whether it ever looks at COMM0 (tools/phase29_md_addr.py).
// GEN_RNW distinguishes the read of $A15120 that d32xr's main_loop_handle_req does from the write
// that every request handler ends with.
reg [23:1] tel_md_addr;
reg  [7:0] tel_md_a151off;
reg [15:0] tel_cp0_rd, tel_cp0_wr;
always @(posedge clk_sys) begin
	if (reset) begin
		tel_md_addr <= 0; tel_md_a151off <= 0; tel_cp0_rd <= 0; tel_cp0_wr <= 0;
	end
	else if (gen_as_d & ~GEN_AS_N) begin
		tel_md_addr <= GEN_VA;
		if (GEN_VA[23:8] == 16'hA151) begin
			tel_md_a151off <= {GEN_VA[7:1],1'b0};
			if (GEN_VA[7:1] == 7'h10) begin		// $A15120
				if (GEN_RNW) tel_cp0_rd <= tel_cp0_rd + 16'd1;
				else         tel_cp0_wr <= tel_cp0_wr + 16'd1;
			end
		end
	end
end
wire [63:0] tel_mdaddr = {tel_md_addr, 1'b0, tel_md_a151off, tel_cp0_rd, tel_cp0_wr};"""),
    ("""	.tel_comm(tel_comm)
);""",
     """	.tel_comm(tel_comm),
	.tel_mdaddr(tel_mdaddr)
);"""),
])

edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_comm      // 32X comm registers + PWM (tools/phase27_comm_regs.py)
);""",
     """	input      [63:0] tel_comm,     // 32X comm registers + PWM (tools/phase27_comm_regs.py)
	input      [63:0] tel_mdaddr    // MD 68000 address + COMM0 traffic (tools/phase29_md_addr.py)
);"""),
    ("reg   [2:0] tel_pend = 0;    // 7=counters 6=audio 5=MCDbus 4=sector 3=SH2PC 2=MD 1=comm",
     "reg   [3:0] tel_pend = 0;    // 8=counters 7=audio 6=MCDbus 5=sector 4=SH2PC 3=MD 2=comm 1=mdaddr"),
    ("\t\tif (&tel_timer) tel_pend <= 3'd7;",
     "\t\tif (&tel_timer) tel_pend <= 4'd8;"),
    ("""				if (tel_pend == 3'd7) begin""",
     """				if (tel_pend == 4'd8) begin"""),
    ("""				end else if (tel_pend == 3'd6) begin
					ram_addr <= BASE_TEL + 25'd1;""",
     """				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd1;"""),
    ("""				end else if (tel_pend == 3'd5) begin
					ram_addr <= BASE_TEL + 25'd2;""",
     """				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd2;"""),
    ("""				end else if (tel_pend == 3'd4) begin
					ram_addr <= BASE_TEL + 25'd3;""",
     """				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd3;"""),
    ("""				end else if (tel_pend == 3'd3) begin
					ram_addr <= BASE_TEL + 25'd4;""",
     """				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd4;"""),
    ("""				end else if (tel_pend == 3'd2) begin
					ram_addr <= BASE_TEL + 25'd5;
					ram_din  <= tel_md;
				end else begin
					ram_addr <= BASE_TEL + 25'd6;
					ram_din  <= tel_comm;
				end""",
     """				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd5;
					ram_din  <= tel_md;
				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd6;
					ram_din  <= tel_comm;
				end else begin
					ram_addr <= BASE_TEL + 25'd7;
					ram_din  <= tel_mdaddr;
				end"""),
])
