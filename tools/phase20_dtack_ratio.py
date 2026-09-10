#!/usr/bin/env python3
"""Quantify the early-DTACK data hazard before it can be made the default.

The A/B on build r9 is unambiguous and repeated 2/2 each way: OSD bit 28 (the reference core's
"acknowledge the sub-CPU when the SDRAM accepts the request" timing) makes mcd-verificator VAR TESTS
pass and moves IRQ TEST from error 0A to error 09 with 227 against jsgroth's expected 224-226. Nothing
regresses.

It is still not safe by construction here. Early DTACK acknowledges the CPU before the data lands, so
S68K_PRGRAM_DO is stale until the SDRAM answers; sdram.sv serves five ports at fixed priority with the
Mega CD PRG-RAM on port 2, BELOW the cartridge port that the MD 68000 and both SH-2s share. phase18's
telemetry measured that latency directly, and it is NOT the "fixed ~60 ns" the reference core assumes:

       min 5 clk_sys (93 ns)      max 15-18 clk_sys (279-335 ns)

With early DTACK the CPU latches roughly 4-5 clk_sys after the acknowledge, so any read whose SDRAM
latency runs past that window returns the previous word. At 1.85M PRG-RAM reads/s even a rate of 1e-6
is a couple of silent corruptions per second, which is exactly the class of bug that made earlier
builds flip between working and dead. The observed maximum proves late reads happen; what is unknown
is how often.

phase18 could not answer that because its over-deadline counter was 16 bits and saturated within a
second - every reading came back 0xFFFF. This widens both counters to 32 bits so the ratio survives,
and makes the threshold selectable so one bitstream answers both questions:

    OSD bit 27 = 0   count reads over 6 clk_sys   -> how many cost a wait state today
                                                    (this is what makes the sub-CPU run slow)
    OSD bit 27 = 1   count reads over 9 clk_sys   -> how many would be CORRUPTED by early DTACK

    beat 3 at 0x30200010:  [63:32] over threshold   [31:0] reads timed

Take two samples and use the delta; the counters free-run from reset.
Usage: phase20_dtack_ratio.py <core dir>"""
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
    ('\t"H2O[28],MCD PRG DTACK,Data,Early;",',
     '\t"H2O[28],MCD PRG DTACK,Data,Early;",\n\t"H2O[27],PRG Lat Thresh,Wait(>6),Hazard(>9);",'),
    ("""localparam [7:0] DTACK_DEADLINE = 8'd6;""",
     """// >6 clk_sys is a wait state (the /DTACK sample is 1.5 CPU clocks = 6.44 clk_sys after /AS).
// >9 is the window early DTACK gives the SDRAM before fx68k takes its final sample, so a read past
// that would hand the CPU the previous word. Selectable so one bitstream measures both.
wire [7:0] DTACK_DEADLINE = status[27] ? 8'd9 : 8'd6;"""),
    ("""reg   [7:0] tel_lat_min, tel_lat_max;
reg  [15:0] tel_lat_slow;
reg  [31:0] tel_lat_n;""",
     """reg   [7:0] tel_lat_min, tel_lat_max;
reg  [31:0] tel_lat_slow;   // 16 bits saturated in ~1 s at 1.85M reads/s (tools/phase20_dtack_ratio.py)
reg  [31:0] tel_lat_n;"""),
    ("""		if (dbg_lat > DTACK_DEADLINE && ~&tel_lat_slow) tel_lat_slow <= tel_lat_slow + 16'd1;""",
     """		if (dbg_lat > DTACK_DEADLINE) tel_lat_slow <= tel_lat_slow + 32'd1;"""),
    ("""wire [63:0] tel_mcdbus = {tel_lat_min, tel_lat_max, tel_lat_slow, tel_lat_n};""",
     """// min/max are known and stable across runs (5 and 15-18 clk_sys); the ratio is what was missing.
wire [63:0] tel_mcdbus = {tel_lat_slow, tel_lat_n};"""),
])
