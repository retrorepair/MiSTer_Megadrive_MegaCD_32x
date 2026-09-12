#!/usr/bin/env python3
"""Time the sub-CPU's /AS-to-/DTACK for the CDC register ports.

WHY
mcd-verificator CDC FLAGS 41 is the last failure: d4 = 48 (pass 48..50) but d5 = 70 (pass 71..73),
total 118 against ~120 needed, deterministic across five runs. d4 and d5 count main<->sub RPC round
trips, and each RPC has the sub-CPU read or write a CDC register on the main CPU's behalf.

Two candidate causes are already eliminated with numbers, on the shipping build:
  * sub-CPU PRG-RAM latency: beat 2 reports 2.41M reads/s with 0.00% over the /DTACK deadline
    (it was 1.38% before the cache), so the sub-CPU no longer waits on memory at all;
  * gate-array register acknowledge: one clk_sys on both sides, ASIC.vhd:613 and :992;
  * and general sub-CPU throughput is bounded to ~0.5% by VAR TESTS, which passes.

What is left is the one thing CDC FLAGS exercises and the passing tests do not: the CDC register
ports themselves. This times them the way tools/phase18 timed PRG-RAM, so the next move is made on
a measurement instead of a guess.

Sub-CPU CDC ports are $FF8004/5 (register index) and $FF8006/7 (register data), which on the
[23:1] word address bus are 0x7FC002 and 0x7FC003.

Repurposes telemetry beat 8 (0x30200040, was tel_trap = {ms_from1, ms_from2}):

    [63:56] min  /AS-to-/DTACK in clk_sys      [55:48] max
    [47:24] accesses over DTACK_DEADLINE       [23: 0] total accesses

Usage: phase60_cdcport_latency.py <core dir>"""
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
    # a second timer beside the PRG-RAM one, armed on the CDC ports instead
    ("""wire [63:0] tel_mcdbus = {tel_lat_slow, tel_lat_n};""",
     """wire [63:0] tel_mcdbus = {tel_lat_slow, tel_lat_n};

// The same measurement for the CDC REGISTER PORTS (tools/phase60_cdcport_latency.py). $FF8004/5 is
// the register index and $FF8006/7 the data, which is 0x7FC002/0x7FC003 on the [23:1] word bus.
// Every main<->sub RPC in the CDC FLAGS test goes through these, and they are the one path that test
// exercises which the passing tests do not.
reg         cdc_as_d = 1, cdc_dtack_d = 1;
reg   [7:0] cdc_lat;
reg         cdc_arm;
reg   [7:0] cdc_lat_min, cdc_lat_max;
reg  [23:0] cdc_lat_slow, cdc_lat_n;

always @(posedge clk_sys) begin
	if (reset) begin
		cdc_as_d <= 1; cdc_dtack_d <= 1; cdc_lat <= 0; cdc_arm <= 0;
		cdc_lat_min <= 8'hFF; cdc_lat_max <= 0; cdc_lat_slow <= 0; cdc_lat_n <= 0;
	end
	else begin
		cdc_as_d    <= MCD_DBG_AS_N;
		cdc_dtack_d <= MCD_DBG_DTACK_N;

		if (cdc_as_d & ~MCD_DBG_AS_N) begin
			cdc_lat <= 0;
			cdc_arm <= (MCD_DBG_A[23:1] == 23'h7FC002) | (MCD_DBG_A[23:1] == 23'h7FC003);
		end
		else if (~MCD_DBG_AS_N && ~&cdc_lat) cdc_lat <= cdc_lat + 8'd1;

		if (cdc_arm & cdc_dtack_d & ~MCD_DBG_DTACK_N) begin
			cdc_arm      <= 0;
			cdc_lat_n    <= cdc_lat_n + 24'd1;
			if (cdc_lat > DTACK_DEADLINE) cdc_lat_slow <= cdc_lat_slow + 24'd1;
			if (cdc_lat < cdc_lat_min) cdc_lat_min <= cdc_lat;
			if (cdc_lat > cdc_lat_max) cdc_lat_max <= cdc_lat;
		end
	end
end"""),

    ("""wire [63:0] tel_trap = {ms_from1, ms_from2};""",
     """wire [63:0] tel_trap = {cdc_lat_min, cdc_lat_max, cdc_lat_slow, cdc_lat_n};	// phase60
wire unused_ms12 = |{ms_from1, ms_from2};"""),
])
