#!/usr/bin/env python3
"""Catch the master SH-2's wild jump itself, not the trap it ends up in.

WHY
Doom CD32X Fusion stalls with the master parked at 0x0000013C, the 32X BIOS's BRA-to-self trap,
while command 0x2E (play_cd_roq_file) is still posted in COMM0 and the MD sits in its main loop
with nothing to do. Everything downstream - the CD read stopping, the sub-CPU idling on the comm
flags, the drive going to STOP - follows from that one crash.

The existing trail (phase30) keeps only the last two distinct PCs, and by the time 0x13C is reached
the master has already walked through the vector table as code, so it only ever reports

    0000013A -> 00000138 -> 0000013C      (and once 060005C0 -> 060005C2 -> 0000013C)

which is the walk, not the cause. Latch on the TRANSITION instead: the moment the PC leaves real
code (cart 0x02xxxxxx / work RAM 0x06xxxxxx, or their cache-through mirrors) for the low BIOS
region, freeze the PC either side of the jump plus the two before it. That names the instruction
that jumped and the context it jumped from.

`game_started` gates the whole thing so the legitimate boot-ROM execution at reset is not mistaken
for the fault.

Also swaps the now-spent PWM fields of DBG_COMM for CP4R. CP4R is $A15128 = MARS_SYS_COMM8, the
register d32xr's RoQ streaming runs on (MARS_ROQFL_REQ bit 0 = "32X wants the next chunk",
STP bit 4), so a stall in the video stream can be read directly. The PWM FIFO fields did their job
in r25 and the drain fix is confirmed.

Beat 8  (0x30200040): {jump_from[31:0], jump_to[31:0]}
Beat 12 (0x30200060): {pc_ctx1[31:0],  pc_ctx2[31:0]}     the two PCs before jump_from

Usage: phase41_jump_trail.py <core dir>"""
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


edit("rtl/S32X/IF.sv", [
    ("""	assign DBG_COMM = {CP0R, CP1R, CP2R,
	                   LPWR.FULL, LPWR.EMPTY, RPWR.FULL, RPWR.EMPTY, PWMCR[11:0]};""",
     """	// CP4R is $A15128 / MARS_SYS_COMM8, the register d32xr streams RoQ video over
	// (bit 0 MARS_ROQFL_REQ, bit 2 EOF, bit 3 NOD, bit 4 STP). The PWM FIFO fields that were
	// here confirmed the r25 drain fix and are no longer needed.
	assign DBG_COMM = {CP0R, CP1R, CP2R, CP4R};"""),
])

edit("MegaCD.sv", [
    ("""// Freeze the master SH-2's last PCs the moment it enters the 32X BIOS exception trap at 0x13C
// (tools/phase30_trap_trail.py). Sampling later only ever shows the trap itself; the instruction
// that caused it is what matters, and it is gone by then. Only the low 28 bits are compared because
// the pipeline's PC carries don't-care upper bits on some fetches.
reg [31:0] trap_pc_d, trap_pc_1, trap_pc_2;
reg        trap_hit;
always @(posedge clk_sys) begin
	if (reset) begin
		trap_pc_d <= 0; trap_pc_1 <= 0; trap_pc_2 <= 0; trap_hit <= 0;
	end
	else if (!trap_hit && S32X_MSH_PC != trap_pc_d) begin
		trap_pc_2 <= trap_pc_1;
		trap_pc_1 <= trap_pc_d;
		trap_pc_d <= S32X_MSH_PC;
		if ((S32X_MSH_PC & 28'hFFFFFFF) == 28'h000013C) trap_hit <= 1;
	end
end
wire [63:0] tel_trap = {trap_pc_1, trap_pc_2};""",
     """// Catch the master SH-2's wild jump itself (tools/phase41_jump_trail.py). The two-deep trail this
// replaces only ever caught the walk through the vector table into the BRA-to-self trap at 0x13C
// (0000013A -> 00000138 -> 0000013C), never the instruction that jumped. Latch on the TRANSITION
// out of real code instead: PC[31:14]==0 is the low BIOS region, and once the game is up the master
// has no business there. game_started gates out the legitimate boot-ROM execution after reset.
reg [31:0] pc_d, pc_1, pc_2;
reg [31:0] jump_from, jump_to, pc_ctx1, pc_ctx2;
reg        jump_hit, game_started;
always @(posedge clk_sys) begin
	if (reset) begin
		pc_d <= 0; pc_1 <= 0; pc_2 <= 0;
		jump_from <= 0; jump_to <= 0; pc_ctx1 <= 0; pc_ctx2 <= 0;
		jump_hit <= 0; game_started <= 0;
	end
	else if (S32X_MSH_PC != pc_d) begin
		// cart ROM, work RAM, and their cache-through mirrors all count as real code
		if (S32X_MSH_PC[27:24] == 4'h2 || S32X_MSH_PC[27:24] == 4'h6) game_started <= 1;
		if (!jump_hit) begin
			pc_2 <= pc_1;
			pc_1 <= pc_d;
			pc_d <= S32X_MSH_PC;
			if (game_started && S32X_MSH_PC[31:14] == 18'd0 && pc_d[31:14] != 18'd0) begin
				jump_hit  <= 1;
				jump_to   <= S32X_MSH_PC;
				jump_from <= pc_d;
				pc_ctx1   <= pc_1;
				pc_ctx2   <= pc_2;
			end
		end
	end
end
wire [63:0] tel_trap = {jump_from, jump_to};"""),
    ("""wire [63:0] tel_int = {S32X_INT, tel_intm_set, tel_intm_clr};""",
     """// repurposed by tools/phase41_jump_trail.py: the two PCs before the wild jump
wire [63:0] tel_int = {pc_ctx1, pc_ctx2};
wire unused_int = |{S32X_INT, tel_intm_set, tel_intm_clr};"""),
])
