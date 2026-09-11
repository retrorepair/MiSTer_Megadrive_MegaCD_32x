#!/usr/bin/env python3
"""Expose the 32X CMD interrupt path, to see whether the master SH-2 is ever told to run.

WHY - the Fusion deadlock is now bounded to two parties:

  68000       spins at $884C08 reading $A15120 (COMM0), waiting for BIT 0 to be set.
              It has STOPPED touching $A120xx entirely, so it is stuck before the point where it
              would release the Mega CD sub-CPU - which is why the sub-CPU sits at SRES=0/SBRQ=1.
  master SH-2 loops calling a cache-purge helper (0201CBC2..C8), i.e. polling memory another CPU
              should have written.

Each is waiting for the other. On hardware the 68000 kicks the master with a CMD interrupt
(d32xr's sh2_wait macro: `move.w #0x0003,0xA15102`), and the master's handler is what sets COMM0
bit 0. If that interrupt never reaches the master, this is exactly the deadlock observed.

    IF.sv:1053   wire CMD_INTM = ICR.INTM & IMMR.CMD;

so it needs BOTH the 68000's ICR write and the master's own mask. ICR.INTM is cleared when the SH-2
writes offset 6'h1A (IF.sv:533). Every one of these paths is byte-identical to pristine upstream, so
the values are what matter.

Beat 12 at DDR3 0x30200060:
       [63:48] ICR    (bit 0 INTM = CMD int pending for master, bit 1 INTS for slave)
       [47:32] IMMR   (master interrupt mask; CMD bit gates the interrupt)
       [31:16] count of ICR.INTM rising edges  - 68000 asserting CMD INT to the master
       [15: 0] count of ICR.INTM falling edges - master acknowledging it

Readings:
  asserts climbing, acks flat  -> the 68000 is kicking the master and the master never takes it:
                                  check IMMR.CMD, and whether the SH-2's interrupt is masked by SR
  asserts flat                 -> the 68000 never kicks it at all; it is stuck earlier than assumed
  both climbing                -> the interrupt path works and the master's handler is failing to
                                  set COMM0 bit 0 for some other reason

Usage: phase34_cmd_int.py <core dir>"""
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
    ("""	output     [63:0] DBG_COMM		// tools/phase27_comm_regs.py""",
     """	output     [63:0] DBG_COMM,		// tools/phase27_comm_regs.py
	output     [31:0] DBG_INT		// tools/phase34_cmd_int.py"""),
    ("""	assign DBG_COMM = {CP0R, CP1R, CP2R,""",
     """	assign DBG_INT = {ICR, IMMR};

	assign DBG_COMM = {CP0R, CP1R, CP2R,"""),
])

edit("rtl/S32X/32X.sv", [
    ("""	output     [63:0] DBG_COMM			// tools/phase27_comm_regs.py
);""",
     """	output     [63:0] DBG_COMM,			// tools/phase27_comm_regs.py
	output     [31:0] DBG_INT			// tools/phase34_cmd_int.py
);"""),
    ("""		.DBG_COMM(DBG_COMM)""",
     """		.DBG_COMM(DBG_COMM),
		.DBG_INT(DBG_INT)"""),
])

edit("MegaCD.sv", [
    ("""	.DBG_COMM(S32X_COMM),""",
     """	.DBG_COMM(S32X_COMM),
	.DBG_INT(S32X_INT),"""),
    ("""wire [63:0] tel_a12 = {tel_a12_off, tel_a12_data, tel_a12_wr, tel_a12_rd};""",
     """wire [63:0] tel_a12 = {tel_a12_off, tel_a12_data, tel_a12_wr, tel_a12_rd};

// 32X CMD interrupt delivery (tools/phase34_cmd_int.py). The 68000 kicks the master with
// $A15102; if that never lands, the master never runs the handler that sets COMM0 bit 0 and the
// two deadlock exactly as observed.
wire [31:0] S32X_INT;
reg         intm_d;
reg  [15:0] tel_intm_set, tel_intm_clr;
always @(posedge clk_sys) begin
	if (reset) begin
		intm_d <= 0; tel_intm_set <= 0; tel_intm_clr <= 0;
	end
	else begin
		intm_d <= S32X_INT[16];			// ICR bit 0 = INTM
		if ( S32X_INT[16] & ~intm_d) tel_intm_set <= tel_intm_set + 16'd1;
		if (~S32X_INT[16] &  intm_d) tel_intm_clr <= tel_intm_clr + 16'd1;
	end
end
wire [63:0] tel_int = {S32X_INT, tel_intm_set, tel_intm_clr};"""),
    ("""	.tel_a12(tel_a12)
);""",
     """	.tel_a12(tel_a12),
	.tel_int(tel_int)
);"""),
])

edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_a12       // MD writes to $A120xx (tools/phase33_a12_writes.py)
);""",
     """	input      [63:0] tel_a12,      // MD writes to $A120xx (tools/phase33_a12_writes.py)
	input      [63:0] tel_int       // 32X CMD interrupt delivery (tools/phase34_cmd_int.py)
);"""),
    ("reg   [3:0] tel_pend = 0;    // 12=counters ... 4=trap 3=cd 2=sub 1=a12",
     "reg   [4:0] tel_pend = 0;    // 13=counters ... 5=trap 4=cd 3=sub 2=a12 1=int"),
    ("\t\tif (&tel_timer) tel_pend <= 4'd12;",
     "\t\tif (&tel_timer) tel_pend <= 5'd13;"),
    ("""				if (tel_pend == 4'd12) begin""",
     """				if (tel_pend == 5'd13) begin"""),
    ("""				end else if (tel_pend == 4'd11) begin
					ram_addr <= BASE_TEL + 25'd1;""",
     """				end else if (tel_pend == 5'd12) begin
					ram_addr <= BASE_TEL + 25'd1;"""),
    ("""				end else if (tel_pend == 4'd10) begin
					ram_addr <= BASE_TEL + 25'd2;""",
     """				end else if (tel_pend == 5'd11) begin
					ram_addr <= BASE_TEL + 25'd2;"""),
    ("""				end else if (tel_pend == 4'd9) begin
					ram_addr <= BASE_TEL + 25'd3;""",
     """				end else if (tel_pend == 5'd10) begin
					ram_addr <= BASE_TEL + 25'd3;"""),
    ("""				end else if (tel_pend == 4'd8) begin
					ram_addr <= BASE_TEL + 25'd4;""",
     """				end else if (tel_pend == 5'd9) begin
					ram_addr <= BASE_TEL + 25'd4;"""),
    ("""				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd5;""",
     """				end else if (tel_pend == 5'd8) begin
					ram_addr <= BASE_TEL + 25'd5;"""),
    ("""				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd6;""",
     """				end else if (tel_pend == 5'd7) begin
					ram_addr <= BASE_TEL + 25'd6;"""),
    ("""				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd7;""",
     """				end else if (tel_pend == 5'd6) begin
					ram_addr <= BASE_TEL + 25'd7;"""),
    ("""				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd8;""",
     """				end else if (tel_pend == 5'd5) begin
					ram_addr <= BASE_TEL + 25'd8;"""),
    ("""				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd9;""",
     """				end else if (tel_pend == 5'd4) begin
					ram_addr <= BASE_TEL + 25'd9;"""),
    ("""				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd10;
					ram_din  <= tel_sub;
				end else begin
					ram_addr <= BASE_TEL + 25'd11;
					ram_din  <= tel_a12;
				end""",
     """				end else if (tel_pend == 5'd3) begin
					ram_addr <= BASE_TEL + 25'd10;
					ram_din  <= tel_sub;
				end else if (tel_pend == 5'd2) begin
					ram_addr <= BASE_TEL + 25'd11;
					ram_din  <= tel_a12;
				end else begin
					ram_addr <= BASE_TEL + 25'd12;
					ram_din  <= tel_int;
				end"""),
])
