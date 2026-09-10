#!/usr/bin/env python3
"""DIAGNOSTIC-ONLY build: keep the machine running past a stalled bus cycle so that EVERY address it
gets stuck on can be collected, and say which master issued each one.

Why: the first probe (phase4) found mcd-verificator stuck on a read of $A11FFC. With the control area
fixed to terminate, it stops at $C00C78 instead - an address that decodes as an invalid VDP mirror
(A[7:5] must be 0) and would hang a real console too. Two things are unknown and cannot be guessed:
whether the 68000, the VDP's DMA fetch or the Z80's banked window issued it, and whether that is the
only such address or the first of many. Stopping at the first one answers neither.

So this build force-terminates a cycle that has sat in MBUS_NOT_USED for ~16k clocks (0.3 ms, far longer
than any real access) and records the last four DISTINCT addresses that needed it. The machine then runs
on and the whole pattern becomes visible in one build instead of one address per build.

*** NEVER SHIP THIS. *** A real Mega Drive waits for /DTACK for ever; auto-terminating is a lie that
happens to be useful for measurement. It lives on branch bushang-probe2 and must not reach a release.

Telemetry beats (read with tools/mister/hpsmem.py):
  0x30200010  [63:48] 0x5334  [47:24] latest stalled address  [23:20] mstate  [19] RNW  [18] seen
              [17] DTACK_N  [16] MEM_RDY  [15:8] captures  [7:6] msrc  [5:4] 0  [3:0] previous mstate
  0x30200018  [63:48] 0x5335  [47:24] previous distinct address  [23:0] the one before that
  0x30200020  [63:48] 0x5336  [47:24] third  [23:0] fourth
              msrc: 0 none, 1 68000, 2 Z80, 3 VDP
Usage: phase5_bushang2.py <core dir>   (apply on top of phase4_bushang_probe.py)"""
import sys, os
d = sys.argv[1]

def edit(rel, pairs):
    p = os.path.join(d, rel)
    s = open(p, encoding="utf-8", errors="replace").read()
    for old, new in pairs:
        assert old in s, rel + ": anchor missing: " + old[:70]
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(s)
    print(rel, "ok")

# 1. ba.sv. The declarations have to move ahead of the state machine, because the state machine now
#    reads stall_kick; SystemVerilog wants them declared before use.
edit("rtl/GEN/ba.sv", [
("	output [63:0] DBG_BUSHANG", "	output [63:0] DBG_BUSHANG,\n	output [63:0] DBG_BUSHANG2,\n	output [63:0] DBG_BUSHANG3"),
("	reg  [15:0] OPEN_BUS;",
 """	reg  [15:0] OPEN_BUS;

	// --- bus-stall probe, declared here because the state machine reads stall_kick (phase5_bushang2.py)
	reg [15:0] stall_cnt;
	reg  [3:0] stall_prev_state;
	reg  [7:0] stall_count;
	reg        stall_seen;
	reg [23:0] stall_addr;
	reg  [3:0] stall_state;
	reg        stall_rnw, stall_dtack, stall_rdy;
	reg  [1:0] stall_msrc;
	reg [23:0] stall_a1, stall_a2, stall_a3;	// the three distinct addresses before the latest
	wire       stall_kick;"""),
# drop the old mid-file declarations, keep the always block
("""	reg [15:0] stall_cnt;
	reg  [3:0] stall_prev_state;
	reg  [7:0] stall_count;
	reg        stall_seen;
	reg [23:0] stall_addr;
	reg  [3:0] stall_state;
	reg        stall_rnw, stall_dtack, stall_rdy;
	always @(posedge CLK) begin""",
 """	always @(posedge CLK) begin"""),
("""					stall_prev_state <= stall_state;
					stall_count <= stall_count + 1'd1;
					stall_seen  <= 1;""",
 """					stall_prev_state <= stall_state;
					stall_msrc  <= msrc;
					stall_count <= stall_count + 1'd1;
					stall_seen  <= 1;
					// keep a short history, skipping repeats of the same address so a single
					// endlessly-retried cycle cannot flush the interesting ones out
					if ({MBUS_A, 1'b0} != stall_addr) begin
						stall_a1 <= stall_addr;
						stall_a2 <= stall_a1;
						stall_a3 <= stall_a2;
					end"""),
("""	assign DBG_BUSHANG = {16'h5334, stall_addr, stall_state, stall_rnw, stall_seen, stall_dtack,
	                      stall_rdy, stall_count, 4'h0, stall_prev_state};""",
 """	// DIAGNOSTIC ONLY: let a cycle that nothing acknowledges give up, so the machine carries on and the
	// next stalling address becomes visible. Real hardware waits for /DTACK indefinitely - see the header
	// of tools/phase5_bushang2.py. Must not appear in a release build.
	assign stall_kick = (mstate == MBUS_NOT_USED) && (&stall_cnt[13:0]) && !stall_cnt[15:14];

	assign DBG_BUSHANG = {16'h5334, stall_addr, stall_state, stall_rnw, stall_seen, stall_dtack,
	                      stall_rdy, stall_count, stall_msrc, 2'b00, stall_prev_state};
	assign DBG_BUSHANG2 = {16'h5335, stall_a1, stall_a2};
	assign DBG_BUSHANG3 = {16'h5336, stall_a3, 24'd0};"""),
("""			MBUS_NOT_USED: begin
					if (!DTACK_N) begin""",
 """			MBUS_NOT_USED: begin
					if (!DTACK_N || stall_kick) begin"""),
])

# 2. gen.sv: pass them up
edit("rtl/GEN/gen.sv", [
("	output [63:0] DBG_BUSHANG", "	output [63:0] DBG_BUSHANG,\n	output [63:0] DBG_BUSHANG2,\n	output [63:0] DBG_BUSHANG3"),
("	.DBG_BUSHANG(DBG_BUSHANG),", "	.DBG_BUSHANG(DBG_BUSHANG),\n	.DBG_BUSHANG2(DBG_BUSHANG2),\n	.DBG_BUSHANG3(DBG_BUSHANG3),"),
])

# 3. top
edit("MegaCD.sv", [
("	.DBG_BUSHANG(bushang)\n);", "	.DBG_BUSHANG(bushang),\n	.DBG_BUSHANG2(bushang2),\n	.DBG_BUSHANG3(bushang3)\n);"),
("wire [63:0] bushang;", "wire [63:0] bushang;\nwire [63:0] bushang2, bushang3;"),
("	.tel_bushang(bushang)\n);", "	.tel_bushang(bushang),\n	.tel_bushang2(bushang2),\n	.tel_bushang3(bushang3)\n);"),
])

# 4. s32x_ddr: two more beats, so the pending counter needs three bits
edit("rtl/s32x_ddr.sv", [
("	input      [63:0] tel_bushang   // stalled MD bus cycle (tools/phase4_bushang_probe.py)",
 "	input      [63:0] tel_bushang,  // stalled MD bus cycle (tools/phase4_bushang_probe.py)\n	input      [63:0] tel_bushang2, // the addresses before it (tools/phase5_bushang2.py)\n	input      [63:0] tel_bushang3"),
("reg   [1:0] tel_pend = 0;    // 3 = counters, 2 = audio, 1 = stalled-bus capture",
 "reg   [2:0] tel_pend = 0;    // 5 = counters, 4 = audio, 3..1 = the stalled-bus capture and its history"),
("		if (&tel_timer) tel_pend <= 2'd3;", "		if (&tel_timer) tel_pend <= 3'd5;"),
("""				case (tel_pend)
					2'd3: begin
						tel_seq  <= tel_seq + 1'd1;
						ram_addr <= BASE_TEL;
						ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
					end
					2'd2: begin
						ram_addr <= BASE_TEL + 25'd1;
						ram_din  <= tel_audio;
					end
					default: begin
						ram_addr <= BASE_TEL + 25'd2;
						ram_din  <= tel_bushang;
					end
				endcase""",
 """				case (tel_pend)
					3'd5: begin
						tel_seq  <= tel_seq + 1'd1;
						ram_addr <= BASE_TEL;
						ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
					end
					3'd4: begin
						ram_addr <= BASE_TEL + 25'd1;
						ram_din  <= tel_audio;
					end
					3'd3: begin
						ram_addr <= BASE_TEL + 25'd2;
						ram_din  <= tel_bushang;
					end
					3'd2: begin
						ram_addr <= BASE_TEL + 25'd3;
						ram_din  <= tel_bushang2;
					end
					default: begin
						ram_addr <= BASE_TEL + 25'd4;
						ram_din  <= tel_bushang3;
					end
				endcase"""),
])
