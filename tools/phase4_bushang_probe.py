#!/usr/bin/env python3
"""Instrument the MD bus so a stalled cycle identifies itself, instead of guessing at the
mcd-verificator "System init..." hang.

Four hypotheses have already been eliminated by build-and-try (region, the /FDC DTACK wait,
cartridge-cycle termination via MEM_RDY, and the data-source mux). This captures the answer directly.

The bus arbiter in rtl/GEN/ba.sv holds `mstate` for the whole of an external cycle and only returns to
MBUS_IDLE when the cycle completes. So: count clocks since mstate last changed, and when that exceeds a
threshold (~16k clk_sys, 0.3 ms - far longer than any legitimate cycle, including a slow SDRAM or Mega CD
answer), latch the bus state. It is then written into the DDR3 telemetry, where hpsmem.py can read it
while the machine sits at "System init...".

Telemetry beat 3, at DDR3 0x30200010:
    [63:48] magic 0x5334
    [47:24] the address of the stalled cycle (MBUS_A, 24 bits)
    [23:20] mstate
    [19]    MBUS_RNW          (1 = read)
    [18]    stalled flag      (sticky: a stall has happened at least once)
    [17]    DTACK_N           (the combined external acknowledge at the moment of capture)
    [16]    MEM_RDY
    [15: 8] how many distinct stalls have been seen (wraps)
    [ 7: 0] mstate at the previous stall, so a repeating pattern is visible

Read it with:  python3 /media/fat/hpsmem.py read 30200010 8
A nonzero magic means the bus really did stall; the address says which device never answered.

Usage: phase4_bushang_probe.py <core dir>
NOTE: needs TELEMETRY = 1 in rtl/s32x_ddr.sv (release builds have it 0).
"""
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

# 1. ba.sv: detect a cycle that never completes and export the state
edit("rtl/GEN/ba.sv", [
("	output  [7:0] DBG_Z80_HOOK", "	output  [7:0] DBG_Z80_HOOK,\n	output [63:0] DBG_BUSHANG"),
("	assign ASEL_N  = MBUS_ASEL_N;",
 """	// Bus-stall probe (tools/phase4_bushang_probe.py): mstate is held for the whole of an external cycle,
	// so if it stops changing for far longer than any legitimate access, that cycle never terminated.
	reg [15:0] stall_cnt;
	reg  [3:0] stall_prev_state;
	reg  [7:0] stall_count;
	reg        stall_seen;
	reg [23:0] stall_addr;
	reg  [3:0] stall_state;
	reg        stall_rnw, stall_dtack, stall_rdy;
	always @(posedge CLK) begin
		reg [3:0] last_state;
		if (!RST_N) begin
			stall_cnt <= 0; stall_seen <= 0; stall_count <= 0; last_state <= 0;
		end
		else begin
			if (mstate != last_state) begin
				last_state <= mstate;
				stall_cnt  <= 0;
			end
			else if (mstate != MBUS_IDLE) begin
				stall_cnt <= stall_cnt + 1'd1;
				if (&stall_cnt[13:0] && !stall_cnt[15:14]) begin	// ~16k clocks, captured once per stall
					stall_addr  <= {MBUS_A, 1'b0};
					stall_state <= mstate;
					stall_rnw   <= MBUS_RNW;
					stall_dtack <= DTACK_N;
					stall_rdy   <= MEM_RDY;
					stall_prev_state <= stall_state;
					stall_count <= stall_count + 1'd1;
					stall_seen  <= 1;
				end
			end
			else stall_cnt <= 0;
		end
	end
	assign DBG_BUSHANG = {16'h5334, stall_addr, stall_state, stall_rnw, stall_seen, stall_dtack,
	                      stall_rdy, stall_count, 4'h0, stall_prev_state};

	assign ASEL_N  = MBUS_ASEL_N;"""),
])

# 2. gen.sv: pass it up
edit("rtl/GEN/gen.sv", [
("	output [23:0] DBG_VA_A", "	output [23:0] DBG_VA_A,\n	output [63:0] DBG_BUSHANG"),
("\t.MEM_RDY(MEM_RDY),\n\t.PAUSE_EN(PAUSE_EN)\n);", "\t.MEM_RDY(MEM_RDY),\n\t.PAUSE_EN(PAUSE_EN),\n\t.DBG_BUSHANG(DBG_BUSHANG)\n);"),
])

# 3. top: wire it to a third telemetry beat
edit("MegaCD.sv", [
("	.DBG_M68K_A(),\n	.DBG_VA_A()\n);", "	.DBG_M68K_A(),\n	.DBG_VA_A(),\n	.DBG_BUSHANG(bushang)\n);"),
("wire        TRANSP_DETECT = 0;", "wire [63:0] bushang;\nwire        TRANSP_DETECT = 0;"),
("	.tel_audio(tel_audio)\n);", "	.tel_audio(tel_audio),\n	.tel_bushang(bushang)\n);"),
])

# 4. s32x_ddr: third beat
edit("rtl/s32x_ddr.sv", [
("	input      [63:0] tel_audio     // audio peaks + sample-enable count (tools/phase3_audio_probe.py)",
 "	input      [63:0] tel_audio,    // audio peaks + sample-enable count (tools/phase3_audio_probe.py)\n	input      [63:0] tel_bushang   // stalled MD bus cycle (tools/phase4_bushang_probe.py)"),
("reg   [1:0] tel_pend = 0;    // 2 = counters beat, 1 = audio beat",
 "reg   [1:0] tel_pend = 0;    // 3 = counters, 2 = audio, 1 = stalled-bus capture"),
("		if (&tel_timer) tel_pend <= 2'd2;", "		if (&tel_timer) tel_pend <= 2'd3;"),
("""				if (tel_pend == 2'd2) begin
					tel_seq  <= tel_seq + 1'd1;
					ram_addr <= BASE_TEL;
					ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
				end else begin
					ram_addr <= BASE_TEL + 25'd1;
					ram_din  <= tel_audio;
				end""",
 """				case (tel_pend)
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
				endcase"""),
("localparam        TELEMETRY = 0;", "localparam        TELEMETRY = 1;"),
])
