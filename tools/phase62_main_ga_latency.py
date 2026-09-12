#!/usr/bin/env python3
"""Time the MAIN CPU's /AS-to-/DTACK for the Mega CD gate-array registers.

STEPPING BACK. jgenesis (issue 105) closed its timing trio by modelling MAIN-CPU behaviour - "stall
the main CPU for 2 out of every 172 mclk cycles", i.e. DRAM refresh. Every probe built here so far
has been on the SUB-CPU side, and all four came back clean. Meanwhile the CDC FLAGS poll loop runs
on the MAIN CPU: each RPC (0x00D4EE write, 0x00D52C read) makes roughly sixteen accesses to
$A12000-$A1202F - two spin-waits, a long address write, a data byte, a command word, a final spin,
and the command clear. That path has only ever been checked by READING ASIC.vhd:613, never measured.

One wait state on each of sixteen accesses is 16 x 2 CPU clocks at 7.67 MHz = 4.2 us per round trip,
against the ~2.8 us per count the test is short. So this is the right order of magnitude and it is
the last unmeasured thing in the loop.

Beat 8 (0x30200040): [63:56] min [55:48] max [47:24] over 68000 deadline [23:0] total, for MD
accesses in $A12000-$A1203F only. The 68000 samples /DTACK at the end of S4, ~195 ns after /AS at
7.67 MHz, which is 10 clk_sys - anything longer costs a wait state.

Usage: phase62_main_ga_latency.py <core dir>"""
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

// MAIN CPU -> Mega CD gate-array register latency (tools/phase62_main_ga_latency.py). The CDC FLAGS
// RPC makes ~16 of these per round trip and it is the last unmeasured path in that loop.
localparam [7:0] MD_DTACK_DEADLINE = 8'd10;   // ~195 ns: /AS to the /DTACK sample at the end of S4
reg         md_as_d = 1, md_dt_d = 1;
reg   [7:0] md_lat, md_min, md_max;
reg         md_arm;
reg  [23:0] md_slow, md_n;

always @(posedge clk_sys) begin
	if (reset) begin
		md_as_d <= 1; md_dt_d <= 1; md_lat <= 0; md_arm <= 0;
		md_min <= 8'hFF; md_max <= 0; md_slow <= 0; md_n <= 0;
	end
	else begin
		md_as_d <= GEN_AS_N;
		md_dt_d <= GEN_DTACK_N;

		if (md_as_d & ~GEN_AS_N) begin
			md_lat <= 0;
			md_arm <= (GEN_VA[23:6] == 18'h28480);          // $A12000-$A1203F
		end
		else if (~GEN_AS_N && ~&md_lat) md_lat <= md_lat + 8'd1;

		if (md_arm & md_dt_d & ~GEN_DTACK_N) begin
			md_arm <= 0;
			md_n   <= md_n + 24'd1;
			if (md_lat > MD_DTACK_DEADLINE) md_slow <= md_slow + 24'd1;
			if (md_lat < md_min) md_min <= md_lat;
			if (md_lat > md_max) md_max <= md_lat;
		end
	end
end"""),
    ("""wire [63:0] tel_trap = {ms_from1, ms_from2};""",
     """wire [63:0] tel_trap = {md_min, md_max, md_slow, md_n};	// phase62
wire unused_ms12 = |{ms_from1, ms_from2};"""),
])
