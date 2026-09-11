#!/usr/bin/env python3
"""Freeze the master SH-2's last PCs before it falls into the 32X BIOS trap.

WHY
The Fusion failure chain is now measured end to end:

  * 68000 spins at $884C08 (Fusion's MD code in the $880000 ROM window):
        move.w (a6),d0 ; beq err ; btst #4,d0 ; move.w (a6),d3 ; btst #0,d3 ; bne go ; ... ; bra
    i.e. waiting for BIT 0 of COMM0 to be set. CP0R reads 0x2E00 for ever: bit 0 never sets.
  * The master SH-2 is the party that should set it, and it is not running game code - its PC sits
    at 0x...013C, which is `BRA .` / `NOP` in the 32X boot ROM (shbios.mif), the catch-all that 53
    exception vectors point at. Reset is 0x140, so 0x13C is reachable ONLY through an exception.
  * Everything else - slave spinning, no frame-buffer writes, black screen - follows from that.

So the question is no longer "where is it stuck" but "what exception put it there", and a PC sample
taken seconds later cannot answer that. This latches the last few distinct PCs and stops updating
the instant the trap address is entered, so the faulting instruction survives to be read out and
disassembled from Fusion's own ROM with tools/dis_sh2.py.

Beat 8 at DDR3 0x30200040:
       [63:32] PC one step before the trap
       [31: 0] PC two steps before the trap
Both zero means the trap was never entered on that run - the master died some other way, or that run
is one of the ones where it keeps executing.

Usage: phase30_trap_trail.py <core dir>"""
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
    ("""wire [63:0] tel_mdaddr = {tel_md_addr, 1'b0, tel_md_a151off, tel_cp0_rd, tel_cp0_wr};""",
     """wire [63:0] tel_mdaddr = {tel_md_addr, 1'b0, tel_md_a151off, tel_cp0_rd, tel_cp0_wr};

// Freeze the master SH-2's last PCs the moment it enters the 32X BIOS exception trap at 0x13C
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
wire [63:0] tel_trap = {trap_pc_1, trap_pc_2};"""),
    ("""	.tel_mdaddr(tel_mdaddr)
);""",
     """	.tel_mdaddr(tel_mdaddr),
	.tel_trap(tel_trap)
);"""),
])

edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_mdaddr    // MD 68000 address + COMM0 traffic (tools/phase29_md_addr.py)
);""",
     """	input      [63:0] tel_mdaddr,   // MD 68000 address + COMM0 traffic (tools/phase29_md_addr.py)
	input      [63:0] tel_trap      // master SH-2 PCs before the BIOS trap (phase30_trap_trail.py)
);"""),
    ("reg   [3:0] tel_pend = 0;    // 8=counters 7=audio 6=MCDbus 5=sector 4=SH2PC 3=MD 2=comm 1=mdaddr",
     "reg   [3:0] tel_pend = 0;    // 9=counters 8=audio 7=MCDbus 6=sector 5=SH2PC 4=MD 3=comm 2=mdaddr 1=trap"),
    ("\t\tif (&tel_timer) tel_pend <= 4'd8;",
     "\t\tif (&tel_timer) tel_pend <= 4'd9;"),
    ("""				if (tel_pend == 4'd8) begin""",
     """				if (tel_pend == 4'd9) begin"""),
    ("""				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd1;""",
     """				end else if (tel_pend == 4'd8) begin
					ram_addr <= BASE_TEL + 25'd1;"""),
    ("""				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd2;""",
     """				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd2;"""),
    ("""				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd3;""",
     """				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd3;"""),
    ("""				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd4;""",
     """				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd4;"""),
    ("""				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd5;""",
     """				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd5;"""),
    ("""				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd6;
					ram_din  <= tel_comm;
				end else begin
					ram_addr <= BASE_TEL + 25'd7;
					ram_din  <= tel_mdaddr;
				end""",
     """				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd6;
					ram_din  <= tel_comm;
				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd7;
					ram_din  <= tel_mdaddr;
				end else begin
					ram_addr <= BASE_TEL + 25'd8;
					ram_din  <= tel_trap;
				end"""),
])
