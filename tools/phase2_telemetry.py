#!/usr/bin/env python3
"""Add DDR3 telemetry to s32x_ddr so the 32X's state can be read live from Linux with tools/mister/hpsmem.py.

Every ~1.2 ms the module writes one 64-bit beat at DDR3 0x30200000:
    [63:48] magic 0x5332          - locate/confirm the write path works at all
    [47:32] seq                   - increments per write; frozen = the core is stuck or DDR3 writes are dead
    [31:24] SH-2 work RAM reads   - low 8 bits of a counter; moving = the SH-2s are executing
    [23:16] SH-2 work RAM writes
    [15: 8] frame-buffer draw writes (SH-2 / 68000 / auto-fill)
    [ 7: 0] display line prefetches completed

Reading it: python3 /media/fat/hpsmem.py read 30200000 8
This is the technique from the global notes (magic + seq + counters), with the address known up front
because we own the memory map. Compiled out by setting S32X_DDR_TELEMETRY to 0.
Usage: phase2_telemetry.py <core/rtl/s32x_ddr.sv>"""
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8", errors="replace").read()

def rep(old, new):
    global s
    assert old in s, "anchor missing: " + old[:70]
    s = s.replace(old, new, 1)

rep("""localparam [14:0] FB_BEATS = 15'd16384;     // 128 KB / 8""",
    """localparam [14:0] FB_BEATS = 15'd16384;     // 128 KB / 8
localparam [24:0] BASE_TEL = 25'h0040000;   // 0x200000 / 8: one telemetry beat (see tools/phase2_telemetry.py)
localparam        TELEMETRY = 1;""")

rep("""reg         lp_pend = 0, lp_fb_q;""",
    """reg         lp_pend = 0, lp_fb_q;
// telemetry counters
reg  [15:0] tel_seq = 0;
reg   [7:0] tel_sdr_rd = 0, tel_sdr_wr = 0, tel_fbd_wr = 0, tel_lp = 0;
reg  [16:0] tel_timer = 0;
reg         tel_pend = 0;""")

rep("""	if (lp_req) begin
		lp_pend   <= 1;
		lp_fb_q   <= lp_fb;
		lp_line_q <= lp_line;
	end""",
    """	if (lp_req) begin
		lp_pend   <= 1;
		lp_fb_q   <= lp_fb;
		lp_line_q <= lp_line;
	end

	// telemetry: count the traffic and ask for a write every ~1.2 ms
	if (TELEMETRY) begin
		if (sdr_rd && !old_sdr_rd) tel_sdr_rd <= tel_sdr_rd + 1'd1;
		if (|sdr_wr && !old_sdr_wr) tel_sdr_wr <= tel_sdr_wr + 1'd1;
		if (|fbd_wr && !old_fbd_wr) tel_fbd_wr <= tel_fbd_wr + 1'd1;
		if (lp_done) tel_lp <= tel_lp + 1'd1;
		tel_timer <= tel_timer + 1'd1;
		if (&tel_timer) tel_pend <= 1;
	end""")

rep("""		S_IDLE: begin
			// priority: display prefetch (deadline) > queued draw writes > SH-2 write > draw read > SH-2 read
			if (lp_pend) begin""",
    """		S_IDLE: begin
			// priority: display prefetch (deadline) > queued draw writes > SH-2 write > draw read > SH-2 read
			if (TELEMETRY && tel_pend) begin
				tel_pend  <= 0;
				tel_seq   <= tel_seq + 1'd1;
				ram_addr  <= BASE_TEL;
				ram_din   <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
				ram_be    <= 8'hFF;
				ram_burst <= 8'd1;
				ram_wr    <= 1;
				state     <= S_WR;
			end
			else if (lp_pend) begin""")

open(p, "w", encoding="utf-8").write(s)
print("telemetry ok")
