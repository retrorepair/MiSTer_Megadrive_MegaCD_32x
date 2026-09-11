#!/usr/bin/env python3
"""Fix the memset-caller probe: count cumulative time in memset, not uninterrupted time.

phase45 reset the counter whenever the PC left the memset range:

    if (ms_in) ms_cnt <= ms_cnt + 1; else ms_cnt <= 0;

The master takes a 60 Hz VBlank interrupt, so the PC leaves memset for the ISR every ~16 ms and
the counter was cleared long before a 0.31 s threshold could be reached. Measured: the probe never
latched across FOUR black-screen boots in which the master was sitting at 0201FD4E/50/52/54.

Reset only when a NEW memset call begins - the prologue at 0201FD18..0201FD20 - so interrupts no
longer clear it while one runaway call is in progress. The threshold then measures cumulative
cycles inside memset for a single call, which is what we actually wanted: a legitimate memset here
totals about 6 ms of in-range time however many interrupts land in the middle of it.

Usage: phase46_memset_caller_fix.py <core dir>"""
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
    ("""wire       ms_in = (S32X_MSH_PC >= 32'h0201FD18) && (S32X_MSH_PC <= 32'h0201FD56);""",
     """wire       ms_in    = (S32X_MSH_PC >= 32'h0201FD18) && (S32X_MSH_PC <= 32'h0201FD56);
// the memset prologue - reaching it means a NEW call, which is the only thing that may reset the
// counter. Leaving the range must NOT: the master's 60 Hz VBlank interrupt does that every ~16 ms.
wire       ms_entry = (S32X_MSH_PC >= 32'h0201FD18) && (S32X_MSH_PC <= 32'h0201FD20);"""),
    ("""		if (ms_in) begin
			ms_cnt <= ms_cnt + 24'd1;
			if (&ms_cnt) begin
				ms_hit   <= 1;
				ms_from1 <= ms_1;
				ms_from2 <= ms_2;
				ms_from3 <= ms_3;
			end
		end
		else ms_cnt <= 24'd0;""",
     """		if (ms_entry) ms_cnt <= 24'd0;
		else if (ms_in) begin
			ms_cnt <= ms_cnt + 24'd1;
			if (&ms_cnt) begin
				ms_hit   <= 1;
				ms_from1 <= ms_1;
				ms_from2 <= ms_2;
				ms_from3 <= ms_3;
			end
		end"""),
])
