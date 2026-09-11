#!/usr/bin/env python3
"""Snapshot the memset caller trail AT CALL TIME, not when the runaway is detected.

phase45/46 kept a trail of distinct PCs seen outside memset and latched it when the in-memset
counter saturated. That reports the wrong thing: the master takes a 60 Hz VBlank interrupt, so
while a long memset runs the PC repeatedly leaves the range into the ISR and overwrites the trail.
Measured - the probe latched 060005F0/F2/F4, which disassembles to

    060005EC  jsr   @r0
    060005EE  ldc   r1,sr
    060005F0  rte            <- returning INTO memset, i.e. memset was already running

so it captured an interrupt return rather than the call site.

Fix: when the memset PROLOGUE runs (0201FD18..0201FD20 = a new call), snapshot the current trail
into pending registers. If that call then turns out to be the runaway one, latch the pending
snapshot. Interrupts during the call can still churn the live trail, but the reported value was
taken before the call began.

Beat 8  (0x30200040): {caller_1, caller_2}
Beat 12 (0x30200060): {caller_3, caller_4}

Usage: phase47_memset_caller_snapshot.py <core dir>"""
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
    ("""reg [31:0] ms_d, ms_1, ms_2, ms_3;
reg [31:0] ms_from1, ms_from2, ms_from3;""",
     """reg [31:0] ms_d, ms_1, ms_2, ms_3, ms_4;
reg [31:0] ms_p1, ms_p2, ms_p3, ms_p4;			// trail snapshotted at the call
reg [31:0] ms_from1, ms_from2, ms_from3, ms_from4;"""),
    ("""		ms_d <= 0; ms_1 <= 0; ms_2 <= 0; ms_3 <= 0;
		ms_from1 <= 0; ms_from2 <= 0; ms_from3 <= 0;""",
     """		ms_d <= 0; ms_1 <= 0; ms_2 <= 0; ms_3 <= 0; ms_4 <= 0;
		ms_p1 <= 0; ms_p2 <= 0; ms_p3 <= 0; ms_p4 <= 0;
		ms_from1 <= 0; ms_from2 <= 0; ms_from3 <= 0; ms_from4 <= 0;"""),
    ("""			if (!ms_in) begin
				ms_3 <= ms_2;
				ms_2 <= ms_1;
				ms_1 <= ms_d;
			end""",
     """			if (!ms_in) begin
				ms_4 <= ms_3;
				ms_3 <= ms_2;
				ms_2 <= ms_1;
				ms_1 <= ms_d;
			end"""),
    ("""		if (ms_entry) ms_cnt <= 24'd0;
		else if (ms_in) begin
			ms_cnt <= ms_cnt + 24'd1;
			if (&ms_cnt) begin
				ms_hit   <= 1;
				ms_from1 <= ms_1;
				ms_from2 <= ms_2;
				ms_from3 <= ms_3;
			end
		end""",
     """		// A new call: reset the counter AND snapshot who called it. Latching the live trail at
		// saturation instead reported the VBlank ISR's RTE, because interrupts leave the memset
		// range constantly while a long call runs.
		if (ms_entry) begin
			ms_cnt <= 24'd0;
			ms_p1  <= ms_1;
			ms_p2  <= ms_2;
			ms_p3  <= ms_3;
			ms_p4  <= ms_4;
		end
		else if (ms_in) begin
			ms_cnt <= ms_cnt + 24'd1;
			if (&ms_cnt) begin
				ms_hit   <= 1;
				ms_from1 <= ms_p1;
				ms_from2 <= ms_p2;
				ms_from3 <= ms_p3;
				ms_from4 <= ms_p4;
			end
		end"""),
    ("""wire [63:0] tel_int = {ms_from3, 32'h00000000};""",
     """wire [63:0] tel_int = {ms_from3, ms_from4};"""),
])
