#!/usr/bin/env python3
"""Time EVERY sub-CPU bus cycle, not just the two regions already cleared.

Three latency probes have come back clean - PRG-RAM reads 0.00% over deadline, gate-array registers
acknowledged in one clk_sys, CDC ports max 5 clk_sys - yet the CDC FLAGS poll period is still ~2.5%
long. Those probes only covered what was hypothesised. This one cannot miss: it arms on every /AS
the sub-CPU asserts and reports the distribution, with a second counter for the gate-array window
($FF8000-$FF81FF) where the RPC's mailbox handshake actually lives.

beat 8  (0x30200040): all accesses      [63:56] min [55:48] max [47:24] over-deadline [23:0] total
beat 11 (0x30200058): $FF80xx accesses  same layout

Usage: phase61_all_sub_latency.py <core dir>"""
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
    ("""wire [63:0] tel_mcdbus = {tel_lat_slow, tel_lat_n};""",
     """wire [63:0] tel_mcdbus = {tel_lat_slow, tel_lat_n};

// Every sub-CPU bus cycle, and separately the gate-array window where the RPC mailbox lives
// (tools/phase61_all_sub_latency.py). The targeted probes all came back clean, so stop targeting.
reg         a_as_d = 1, a_dtack_d = 1;
reg   [7:0] a_lat;
reg         a_arm, g_arm;
reg   [7:0] a_min, a_max, g_min, g_max;
reg  [23:0] a_slow, a_n, g_slow, g_n;

always @(posedge clk_sys) begin
	if (reset) begin
		a_as_d <= 1; a_dtack_d <= 1; a_lat <= 0; a_arm <= 0; g_arm <= 0;
		a_min <= 8'hFF; a_max <= 0; a_slow <= 0; a_n <= 0;
		g_min <= 8'hFF; g_max <= 0; g_slow <= 0; g_n <= 0;
	end
	else begin
		a_as_d    <= MCD_DBG_AS_N;
		a_dtack_d <= MCD_DBG_DTACK_N;

		if (a_as_d & ~MCD_DBG_AS_N) begin
			a_lat <= 0;
			a_arm <= 1;
			g_arm <= (MCD_DBG_A[23:9] == 15'h7FC0);      // $FF8000-$FF81FF
		end
		else if (~MCD_DBG_AS_N && ~&a_lat) a_lat <= a_lat + 8'd1;

		if (a_arm & a_dtack_d & ~MCD_DBG_DTACK_N) begin
			a_arm <= 0; g_arm <= 0;
			a_n   <= a_n + 24'd1;
			if (a_lat > DTACK_DEADLINE) a_slow <= a_slow + 24'd1;
			if (a_lat < a_min) a_min <= a_lat;
			if (a_lat > a_max) a_max <= a_lat;
			if (g_arm) begin
				g_n <= g_n + 24'd1;
				if (a_lat > DTACK_DEADLINE) g_slow <= g_slow + 24'd1;
				if (a_lat < g_min) g_min <= a_lat;
				if (a_lat > g_max) g_max <= a_lat;
			end
		end
	end
end"""),
    ("""wire [63:0] tel_trap = {ms_from1, ms_from2};""",
     """wire [63:0] tel_trap = {a_min, a_max, a_slow, a_n};	// phase61: all sub-CPU accesses
wire unused_ms12 = |{ms_from1, ms_from2};"""),
    ("""wire [63:0] tel_a12 = {tel_a12_off, tel_a12_data, tel_a12_wr, tel_a12_rd};""",
     """wire [63:0] tel_a12 = {g_min, g_max, g_slow, g_n};	// phase61: $FF80xx accesses
wire unused_a12 = |{tel_a12_off, tel_a12_data, tel_a12_wr, tel_a12_rd};"""),
])
