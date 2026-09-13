#!/usr/bin/env python3
"""Stop the 32X losing horizontal lock to the MD for good.

WHY - measured, not argued
Night Trap's 32X layer sits a long way left of where it belongs. tools/mister/ntshot.py grabs a
MiSTer screenshot and both 32X frame buffers out of the shared DDR3 at the same instant, and
tools/fbrender.py + tools/fbshift.py say what happened to the picture between memory and screen:

  * the frame buffer is CORRECT - line table a clean 160-word ramp from word 0x100, picture centred
    and full width;
  * the screen shows that same picture translated bodily left, intact, unclipped, unstretched;
  * the translation is the SAME on every line of a frame (dx -58..-65 across all 40 lines carrying
    content on a frozen frame, 87% median match), so it is not a per-line prefetch race;
  * it is stable within a core load and different between loads: -68, -75, -111 px;
  * it survives the game CRASHING, with nothing writing DDR3 at all, so it is not bus contention;
  * and cart 32X is pixel-perfect on the same RTL - Doom 32X measures zero displacement on every
    line.

THE MECHANISM
VDP.sv resynchronised H_CNT to the MD's HSYNC only while H_CNT >= 0x160. That is a test on the
counter's PHASE. The 32X display window opens 72 dots after the resync point (0x1CE -> 0x17 through
the 9-bit wrap), so if H_CNT reads X instead of 0x1CE when HSYNC falls, the layer is displaced by
X - 0x1CE dots. Running the three measurements backwards gives X = 0x12, 0x19 and 0x3D - every one
of them just outside the accept window. Once the phase is outside that window the resync can never
fire again, and because the free-run period (420) equals the MD's H40 line the wrong phase then
persists for ever. It is a permanent lock failure, not a drift, which is why the offset is rock
steady and why nothing in the game recovers it.

Cart 32X escapes it only by luck: the 32X leaves reset with the MD and lands inside the window. On
CD the Mega CD BIOS starts the 32X much later, so the phase lands wherever it lands - hence "mostly
way left, but sometimes way right".

THE FIX
Test TIME instead of phase: take the MD's HSYNC once SYNC_GUARD dots have passed since the last one
taken. That still ignores a second edge inside the same line, which is all the old guard usefully
did - when the 32X is locked, H_CNT is 0x1CE at HSYNC and a full line has elapsed, so old and new
accept identically, which is why cart 32X is unaffected - but it cannot be fooled by phase, so the
32X can no longer sit permanently out of lock. Being a slave to the MD's HSYNC is what the real
hardware is.

The new behaviour is the DEFAULT; set OSD bit 49 for the upstream guard, so one bitstream A/Bs it.
Telemetry beat 8 (0x30200040) carries the proof:

    [24:16] H_CNT at the last HSYNC falling edge   (healthy: 0x1CE)
    [15: 8] HSYNC edges TAKEN, saturating          (healthy: climbing)
    [ 7: 0] HSYNC edges REFUSED, saturating        (healthy: 0; the fault saturates it)

Usage: phase65_hsync_relock.py <core dir>"""
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


edit("rtl/S32X/VDP.sv", [
    # ---- ports
    ("\toutput      [7:0] DBG_DOT_TIME\n);",
     "\toutput      [7:0] DBG_DOT_TIME,\n"
     "\n"
     "\tinput             SYNC_RELOCK,\t// phase-independent horizontal lock (tools/phase65_hsync_relock.py)\n"
     "\toutput     [31:0] DBG_SYNC\n);"),

    # ---- state
    ("\tbit        EDCLK_OLD;\n",
     "\tbit        EDCLK_OLD;\n"
     "\tlocalparam [8:0] SYNC_GUARD = 9'd300;\t// no legitimate HSYNC comes sooner than a line (342 H32, 420 H40)\n"
     "\tbit  [8:0] SINCE_HS;\t\t\t// dots since the HSYNC we last took\n"
     "\tbit  [8:0] DBG_HS_HCNT;\n"
     "\tbit  [7:0] DBG_HS_ACC, DBG_HS_REJ;\n"),

    # ---- reset
    ("\t\t\tDOT_CLK <= 0;\n"
     "\t\t\tH_CNT <= '0;\n"
     "\t\t\tV_CNT <= '0;\n"
     "\t\t\tHSYNC_N_OLD <= 1;\n"
     "\t\t\tVSYNC_N_OLD <= 1;\n",
     "\t\t\tDOT_CLK <= 0;\n"
     "\t\t\tH_CNT <= '0;\n"
     "\t\t\tV_CNT <= '0;\n"
     "\t\t\tHSYNC_N_OLD <= 1;\n"
     "\t\t\tVSYNC_N_OLD <= 1;\n"
     "\t\t\tSINCE_HS <= '0;\n"
     "\t\t\tDBG_HS_HCNT <= '0;\n"
     "\t\t\tDBG_HS_ACC <= '0;\n"
     "\t\t\tDBG_HS_REJ <= '0;\n"),

    # ---- the guard itself
    ("\t\t\t\tif (!HSYNC_N_SYNC && HSYNC_N_OLD && H_CNT >= 9'h160) begin\n"
     "\t\t\t\t\tH_CNT <= 9'h1CE;\n"
     "\t\t\t\t\tDOT_CLK <= 1;\n"
     "\t\t\t\tend else if (H_CNT == 9'h16C && DOT_CLK) begin\n"
     "\t\t\t\t\tH_CNT <= 9'h1C9;\n"
     "\t\t\t\tend else if (DOT_CLK) begin\n"
     "\t\t\t\t\tH_CNT <= H_CNT + 9'd1;\n"
     "\t\t\t\tend\n",
     "\t\t\t\t// HORIZONTAL LOCK (tools/phase65_hsync_relock.py). This used to accept the MD's HSYNC\n"
     "\t\t\t\t// only while H_CNT >= 0x160, a test on the counter's PHASE. The display window opens\n"
     "\t\t\t\t// 72 dots after the resync point (0x1CE -> 0x17 through the 9-bit wrap), so an H_CNT of\n"
     "\t\t\t\t// X at HSYNC displaces the whole layer by X - 0x1CE dots. Night Trap measured 68, 75 and\n"
     "\t\t\t\t// 111 px left over three core loads - X = 0x12, 0x19, 0x3D, every one just outside the\n"
     "\t\t\t\t// window - with a correct frame buffer, the same displacement on every line, and the\n"
     "\t\t\t\t// fault surviving the game crashing. Once the phase is outside the window the resync can\n"
     "\t\t\t\t// never fire again, and since the free-run period below (420) equals the MD's H40 line,\n"
     "\t\t\t\t// the wrong phase then persists for ever. Cart 32X escapes it only because the 32X leaves\n"
     "\t\t\t\t// reset with the MD and lands inside the window; on CD the BIOS starts it much later.\n"
     "\t\t\t\t// So test TIME, not phase: take HSYNC once a line's worth of dots has passed since the\n"
     "\t\t\t\t// last one taken. A second edge inside the same line is still ignored, which is all the\n"
     "\t\t\t\t// old guard usefully did - locked, H_CNT is 0x1CE at HSYNC and SINCE_HS is a full line,\n"
     "\t\t\t\t// so both forms accept identically - but phase can no longer lock the 32X out.\n"
     "\t\t\t\tif (!HSYNC_N_SYNC && HSYNC_N_OLD) DBG_HS_HCNT <= H_CNT;\n"
     "\t\t\t\tif (!HSYNC_N_SYNC && HSYNC_N_OLD &&\n"
     "\t\t\t\t    (SYNC_RELOCK ? (SINCE_HS >= SYNC_GUARD) : (H_CNT >= 9'h160))) begin\n"
     "\t\t\t\t\tH_CNT <= 9'h1CE;\n"
     "\t\t\t\t\tDOT_CLK <= 1;\n"
     "\t\t\t\t\tSINCE_HS <= '0;\n"
     "\t\t\t\t\tif (~&DBG_HS_ACC) DBG_HS_ACC <= DBG_HS_ACC + 8'd1;\n"
     "\t\t\t\tend else begin\n"
     "\t\t\t\t\tif (!HSYNC_N_SYNC && HSYNC_N_OLD && ~&DBG_HS_REJ) DBG_HS_REJ <= DBG_HS_REJ + 8'd1;\n"
     "\t\t\t\t\tif (H_CNT == 9'h16C && DOT_CLK) begin\n"
     "\t\t\t\t\t\tH_CNT <= 9'h1C9;\n"
     "\t\t\t\t\tend else if (DOT_CLK) begin\n"
     "\t\t\t\t\t\tH_CNT <= H_CNT + 9'd1;\n"
     "\t\t\t\t\tend\n"
     "\t\t\t\t\tif (DOT_CLK && ~&SINCE_HS) SINCE_HS <= SINCE_HS + 9'd1;\n"
     "\t\t\t\tend\n"),

    # ---- readout
    ("\tassign DOT_CE = DOT_CLK & ~EDCLK_SYNC & EDCLK_OLD;",
     "\tassign DOT_CE = DOT_CLK & ~EDCLK_SYNC & EDCLK_OLD;\n"
     "\n"
     "\t// What the horizontal lock is doing. Locked and healthy reads H_CNT = 0x1CE with ACC climbing\n"
     "\t// and REJ at zero; the Night Trap fault reads an H_CNT well below 0x160 with REJ saturated.\n"
     "\tassign DBG_SYNC = {7'd0, DBG_HS_HCNT, DBG_HS_ACC, DBG_HS_REJ};"),
])

edit("rtl/S32X/32X.sv", [
    ("\toutput     [23:0] DBG_CA,",
     "\toutput     [23:0] DBG_CA,\n"
     "\tinput             SYNC_RELOCK,\t// tools/phase65_hsync_relock.py\n"
     "\toutput     [31:0] DBG_SYNC,"),
    ("\t\t.YSO_N(YSO_N)\n\t);",
     "\t\t.YSO_N(YSO_N),\n"
     "\n"
     "\t\t.SYNC_RELOCK(SYNC_RELOCK),\n"
     "\t\t.DBG_SYNC(DBG_SYNC)\n\t);"),
])

edit("MegaCD.sv", [
    ("wire  [4:0] S32X_R, S32X_G, S32X_B;",
     "wire  [4:0] S32X_R, S32X_G, S32X_B;\n"
     "wire [31:0] S32X_DBG_SYNC;"),
    ("\t.DBG_CA()",
     "\t.DBG_CA(),\n"
     "\t.SYNC_RELOCK(~status[49]),   // phase-independent 32X horizontal lock, DEFAULT ON; set bit 49 for upstream\n"
     "\t.DBG_SYNC(S32X_DBG_SYNC)"),
    ("wire [63:0] tel_trap = {ms_from1, ms_from2};",
     "wire [63:0] tel_trap = {32'd0, S32X_DBG_SYNC};\t// phase65: the 32X horizontal lock\n"
     "wire unused_ms12 = |{ms_from1, ms_from2};"),
    ("\t\"H2O[57],MCD PRG posted writes,On,Off;\",",
     "\t\"H2O[57],MCD PRG posted writes,On,Off;\",\n"
     "\t\"H2O[49],32X H-lock by time,On,Off;\","),
])
