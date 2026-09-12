#!/usr/bin/env python3
"""Time the MAIN CPU's /AS-to-/DTACK for CARTRIDGE ROM fetches.

THE LAST UNMEASURED PATH. Everything else in the CDC FLAGS RPC loop is now measured clean: sub-CPU
PRG-RAM, CDC ports, the whole sub-CPU bus, and the main CPU's gate-array accesses (0-1 clk_sys). And
the numbers say where the time actually goes - the sub-CPU answers within one 2.08 us poll, yet an
RPC costs ~55 us, which is ~420 main-CPU clocks: the round trip is MAIN-CPU EXECUTION bound, and
that code is fetched from cartridge ROM on the shared SDRAM port.

That is the same port the whole contention thesis was about. The PRG-RAM cache removed the sub-CPU's
13.7% occupancy, which is why REG 8030, VAR TESTS and IRQ closed - but refresh, the remaining cache
misses and PCM still contend for it, and nobody has ever measured what an MD instruction fetch
actually costs.

Beat 8 (0x30200040): [63:56] min [55:48] max [47:24] over deadline [23:0] total, for MD accesses
below $400000. The 68000 samples /DTACK at the end of S4, ~195 ns = 10 clk_sys after /AS.

Usage: phase63_main_cart_latency.py <core dir>"""
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

// MAIN CPU cartridge-ROM fetch latency (tools/phase63_main_cart_latency.py) - the last unmeasured
// path in the CDC FLAGS loop, and the one the SDRAM contention thesis was always about.
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
			md_arm <= ~|GEN_VA[23:22];                     // $000000-$3FFFFF, the cartridge
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
     """wire [63:0] tel_trap = {md_min, md_max, md_slow, md_n};	// phase63
wire unused_ms12 = |{ms_from1, ms_from2};"""),
])
