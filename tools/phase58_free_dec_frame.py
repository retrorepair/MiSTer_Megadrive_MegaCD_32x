#!/usr/bin/env python3
"""Let the CDC decoder frame timer free-run, as the hardware's does.

WHY - measured, not argued
mcd-verificator CDC FLAGS 41 wants 71 <= d5 <= 73 and we read 70. d4 and d5 count main<->sub RPC
round trips in the two phases of ONE decoder-interrupt cycle, so they are set by the DECI waveform's
period and duty. Sampling the DEC_FRAME and DEC_MID event counters live (scratch/deciwatch.py, beat
3) while the verificator runs shows the waveform is not what it should be:

    t=5.0  SECTOR_END +6   DEC_FRAME +22   DEC_MID +25
    t=7.0  SECTOR_END +0   DEC_FRAME  +5   DEC_MID  +6
    t=14.0 SECTOR_END +3   DEC_FRAME +27   DEC_MID +29

DEC_MID fires MORE OFTEN than DEC_FRAME. The cause is right here: SECTOR_END resets FRAME_CNT but
does NOT pulse DEC_FRAME, so a sector arriving after the 40% mark cancels that frame's DECI
assertion outright and restarts the count. Assertions go missing and the phase boundaries slip.

THE HARDWARE
The decoder's 75 Hz interrupt free-runs. jgenesis issue 105, sub-test 30: "Decoder interrupts should
trigger at 75Hz when enabled (DECEN + DECIEN), EVEN IF the decoder is not receiving new sectors from
the CDD." And this file's own comment already says it: "real silicon has no such latch; its frame
counter free-runs". The drive resync was added on the assumption that real data and the free-running
frame should coincide; on hardware they simply both run at 75 Hz and nothing resynchronises anything.

So: drop the SECTOR_END reset. DECEN still holds the counter cleared while the decoder is off, which
is what turning the decoder off means. 53693175 / 75 = 715909 clocks per frame, DEC_MID at 286363 =
40.00% of it, both then firing exactly 75 times a second with a stable duty.

Usage: phase58_free_dec_frame.py <core dir>"""
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


edit("rtl/MCD/CDC.vhd", [
    ("""			if CTRL0(DECEN) = '0' or SECTOR_END = '1' then
				FRAME_CNT <= (others => '0');""",
     """			-- FREE-RUNNING (tools/phase58_free_dec_frame.py). SECTOR_END used to reset this counter
			-- as well, on the idea that the drive's sector stream and the frame should be kept in
			-- step. It does the opposite: the reset does not pulse DEC_FRAME, so a sector arriving
			-- after FRAME_MID cancelled that frame's DECI assertion and restarted the count.
			-- Measured live during mcd-verificator, DEC_MID fired MORE OFTEN than DEC_FRAME
			-- (+25 against +22, +29 against +27) - assertions were going missing.
			-- The hardware's decoder interrupt free-runs at 75 Hz whether or not sectors are
			-- arriving; DECEN off is the only thing that stops it.
			if CTRL0(DECEN) = '0' then
				FRAME_CNT <= (others => '0');"""),
])
