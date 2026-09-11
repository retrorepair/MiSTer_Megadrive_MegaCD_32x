#!/usr/bin/env python3
"""Capture what the MD 68000 actually writes to the Mega CD gate array at $A120xx.

WHY - measured on r18 with Fusion running:

    SRES=0  SBRQ=1  AS_N=1  DTACK_N=1   sub-CPU /AS cycles frozen
    sub-CPU PRG-RAM reads frozen        it is not executing at all
    it stops at a DIFFERENT address every run (007C40, 00A03E, 005E76)

Stopping at an arbitrary address means it was halted externally rather than dying on an instruction,
and SRES=0/SBRQ=1 is exactly the state `write_byte(0xA12001, 0x02)` produces - reset asserted, bus
requested. Fusion does that legitimately to upload its sub-CPU program and for later transfers
(src-md/scd.c), then releases with `write_byte(0xA12001, 0x01)`.

The 68000 is meanwhile spinning at $884C08 reading $A12000 and testing bit 0 - SRES - which the
ASIC read path correctly reports as 0 (ASIC.vhd:721). ASIC.vhd assigns SRES only at reset and from
`SRES <= EXT_VDI(0)` on an LDS write (ASIC.vhd:616), and that path is byte-identical to the b66
reference. So either the 68000 is not writing 0x01, or its writes are not reaching the gate array.

This settles it by capturing the traffic at the top level, before any Mega CD decode, so it is
independent of the ASIC entirely. Debug bit 39 (the EXT_AS_N source) has already been A/B'd and makes
no difference.

Beat 11 at DDR3 0x30200058:
       [63:56] last $A120xx write offset (A7:A1 << 1)
       [55:40] last $A120xx write data
       [39:20] count of MD writes to $A120xx
       [19: 0] count of MD reads  of $A120xx

Readings:
  last write = offset 00, data xxx1 -> the 68000 IS asking for the sub-CPU to run and the gate array
                                       is ignoring it: the bug is in the write path/qualification
  last write = offset 00, data xxx2 -> it is still holding reset deliberately; something earlier in
                                       its sequence never completed, so look at what it is waiting on
  write count static                 -> it is not writing $A120xx at all any more

Usage: phase33_a12_writes.py <core dir>"""
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
    ("""wire [63:0] tel_sub = {MCD_DBG_A[23:1], 1'b0,""",
     """// What the 68000 writes to the gate array (tools/phase33_a12_writes.py). Captured on the raw MD
// bus so it is independent of the Mega CD decode: SRES is only ever set by an LDS write of bit 0 to
// $A12001, and it is stuck at 0 while the sub-CPU is held.
reg  [7:0] tel_a12_off;
reg [15:0] tel_a12_data;
reg [19:0] tel_a12_wr, tel_a12_rd;
always @(posedge clk_sys) begin
	if (reset) begin
		tel_a12_off <= 0; tel_a12_data <= 0; tel_a12_wr <= 0; tel_a12_rd <= 0;
	end
	else if (gen_as_d & ~GEN_AS_N && GEN_VA[23:8] == 16'hA120) begin
		if (GEN_RNW) tel_a12_rd <= tel_a12_rd + 20'd1;
		else begin
			tel_a12_wr   <= tel_a12_wr + 20'd1;
			tel_a12_off  <= {GEN_VA[7:1],1'b0};
			tel_a12_data <= GEN_VDO;
		end
	end
end
wire [63:0] tel_a12 = {tel_a12_off, tel_a12_data, tel_a12_wr, tel_a12_rd};

wire [63:0] tel_sub = {MCD_DBG_A[23:1], 1'b0,"""),
    ("""	.tel_sub(tel_sub)
);""",
     """	.tel_sub(tel_sub),
	.tel_a12(tel_a12)
);"""),
])

edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_sub       // sub-CPU halt state (tools/phase32_subcpu_halt.py)
);""",
     """	input      [63:0] tel_sub,      // sub-CPU halt state (tools/phase32_subcpu_halt.py)
	input      [63:0] tel_a12       // MD writes to $A120xx (tools/phase33_a12_writes.py)
);"""),
    ("reg   [3:0] tel_pend = 0;    // 11=counters ... 3=trap 2=cd 1=sub",
     "reg   [3:0] tel_pend = 0;    // 12=counters ... 4=trap 3=cd 2=sub 1=a12"),
    ("\t\tif (&tel_timer) tel_pend <= 4'd11;",
     "\t\tif (&tel_timer) tel_pend <= 4'd12;"),
    ("""				if (tel_pend == 4'd11) begin""",
     """				if (tel_pend == 4'd12) begin"""),
    ("""				end else if (tel_pend == 4'd10) begin
					ram_addr <= BASE_TEL + 25'd1;""",
     """				end else if (tel_pend == 4'd11) begin
					ram_addr <= BASE_TEL + 25'd1;"""),
    ("""				end else if (tel_pend == 4'd9) begin
					ram_addr <= BASE_TEL + 25'd2;""",
     """				end else if (tel_pend == 4'd10) begin
					ram_addr <= BASE_TEL + 25'd2;"""),
    ("""				end else if (tel_pend == 4'd8) begin
					ram_addr <= BASE_TEL + 25'd3;""",
     """				end else if (tel_pend == 4'd9) begin
					ram_addr <= BASE_TEL + 25'd3;"""),
    ("""				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd4;""",
     """				end else if (tel_pend == 4'd8) begin
					ram_addr <= BASE_TEL + 25'd4;"""),
    ("""				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd5;""",
     """				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd5;"""),
    ("""				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd6;""",
     """				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd6;"""),
    ("""				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd7;""",
     """				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd7;"""),
    ("""				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd8;""",
     """				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd8;"""),
    ("""				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd9;
					ram_din  <= tel_cd;
				end else begin
					ram_addr <= BASE_TEL + 25'd10;
					ram_din  <= tel_sub;
				end""",
     """				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd9;
					ram_din  <= tel_cd;
				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd10;
					ram_din  <= tel_sub;
				end else begin
					ram_addr <= BASE_TEL + 25'd11;
					ram_din  <= tel_a12;
				end"""),
])
