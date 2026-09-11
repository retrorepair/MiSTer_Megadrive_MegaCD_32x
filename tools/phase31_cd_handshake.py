#!/usr/bin/env python3
"""Expose the Mega CD main/sub communication flags, to find where Fusion's CD read stalls.

WHY - the chain is now measured end to end:

  master SH-2 posts 0x2E in COMM0 and waits          CP0R stuck at 0x2E00
  0x2E = prireqtbl index 46 = play_cd_roq_file       (d32xr src-md/crt0.s)
  68000 spins at $884C08 waiting for bit 0 of COMM0  (disassembled from Fusion's own ROM)
  SECTOR_END = 0.0/s                                 no CD sectors are being delivered at all

Night Trap, which boots FROM the disc, gets 75 sectors/s on the same build. Fusion boots from the
CART and uploads its own sub-CPU program (src-md/cd.s incbins cd/cd.bin) - full Mega CD Mode 1. So
the failing piece is a Mode-1 sub-CPU program trying to read a file, and the handshake it uses is
the gate array's communication flags:

    $A1200E  CFM  main -> sub command byte   (ASIC.vhd:646)
    $A1200F  CFS  sub -> main status byte    (ASIC.vhd:1003)

From src-md/scd.c the protocol is: the sub program writes 'I' (0x49) once alive, then 0 when ready
for commands; the 68000 writes a command letter to CFM and waits for CFS to go non-zero, then writes
0 to CFM to acknowledge. Both sides poll with NO timeout once past init.

Beat 9 at DDR3 0x30200048:
       [63:56] CFM   main -> sub command byte
       [55:48] CFS   sub  -> main status byte
       [47:32] CFS change count   (is the sub program alive and answering at all?)
       [31:16] CFM change count   (is the 68000 still issuing commands?)
       [15: 0] reserved

Readings:
  CFS = 0x00, CFM = 0x00, neither changing -> the sub program is idle and nobody is asking: the
                                              68000 never got as far as issuing the file read
  CFM = a letter, CFS = 0x00, CFS static   -> the 68000 asked and the sub program never answered:
                                              the uploaded sub-CPU program is not running properly
  CFS = 0x49 ('I') static                  -> it announced itself but never became ready
  both changing                            -> the handshake works and the stall is deeper, in the
                                              CDC/CDD path (SECTOR_END would confirm)

Usage: phase31_cd_handshake.py <core dir>"""
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


edit("rtl/MCD/ASIC.vhd", [
    ("""		DBG_EARLY_DTACK: in std_logic;""",
     """		DBG_EARLY_DTACK: in std_logic;
		DBG_CFM			: out std_logic_vector(7 downto 0);	-- tools/phase31_cd_handshake.py
		DBG_CFS			: out std_logic_vector(7 downto 0);"""),
    ("""	EXT_DTACK_N <= """,
     """	-- the gate array's communication flags, $A1200E / $A1200F
	DBG_CFM <= CFM;
	DBG_CFS <= CFS;

	EXT_DTACK_N <= """),
])

edit("rtl/MCD/MCD.vhd", [
    ("""		DBG_SECTOR_END	: out std_logic;""",
     """		DBG_CFM			: out std_logic_vector(7 downto 0);	-- tools/phase31_cd_handshake.py
		DBG_CFS			: out std_logic_vector(7 downto 0);
		DBG_SECTOR_END	: out std_logic;"""),
    ("""		DBG_EARLY_DTACK => DBG_EARLY_DTACK,""",
     """		DBG_EARLY_DTACK => DBG_EARLY_DTACK,
		DBG_CFM         => DBG_CFM,
		DBG_CFS         => DBG_CFS,"""),
])

edit("MegaCD.sv", [
    ("""	.DBG_SECTOR_END(MCD_DBG_SECTOR_END),""",
     """	.DBG_CFM(MCD_DBG_CFM),
	.DBG_CFS(MCD_DBG_CFS),
	.DBG_SECTOR_END(MCD_DBG_SECTOR_END),"""),
    ("""wire [63:0] tel_trap = {trap_pc_1, trap_pc_2};""",
     """wire [63:0] tel_trap = {trap_pc_1, trap_pc_2};

// Mega CD main/sub communication flags (tools/phase31_cd_handshake.py). Fusion's master is waiting
// on play_cd_roq_file and no sectors are being delivered, so the question is whether the Mode-1
// sub-CPU program it uploaded is answering at all.
wire  [7:0] MCD_DBG_CFM, MCD_DBG_CFS;
reg   [7:0] cfm_d, cfs_d;
reg  [15:0] tel_cfm_chg, tel_cfs_chg;
always @(posedge clk_sys) begin
	if (reset) begin
		cfm_d <= 0; cfs_d <= 0; tel_cfm_chg <= 0; tel_cfs_chg <= 0;
	end
	else begin
		cfm_d <= MCD_DBG_CFM;
		cfs_d <= MCD_DBG_CFS;
		if (MCD_DBG_CFM != cfm_d) tel_cfm_chg <= tel_cfm_chg + 16'd1;
		if (MCD_DBG_CFS != cfs_d) tel_cfs_chg <= tel_cfs_chg + 16'd1;
	end
end
wire [63:0] tel_cd = {MCD_DBG_CFM, MCD_DBG_CFS, tel_cfs_chg, tel_cfm_chg, 16'h0000};"""),
    ("""	.tel_trap(tel_trap)
);""",
     """	.tel_trap(tel_trap),
	.tel_cd(tel_cd)
);"""),
])

edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_trap      // master SH-2 PCs before the BIOS trap (phase30_trap_trail.py)
);""",
     """	input      [63:0] tel_trap,     // master SH-2 PCs before the BIOS trap (phase30_trap_trail.py)
	input      [63:0] tel_cd        // Mega CD comm flags (tools/phase31_cd_handshake.py)
);"""),
    ("reg   [3:0] tel_pend = 0;    // 9=counters 8=audio 7=MCDbus 6=sector 5=SH2PC 4=MD 3=comm 2=mdaddr 1=trap",
     "reg   [3:0] tel_pend = 0;    // 10=counters 9=audio 8=MCDbus 7=sector 6=SH2PC 5=MD 4=comm 3=mdaddr 2=trap 1=cd"),
    ("\t\tif (&tel_timer) tel_pend <= 4'd9;",
     "\t\tif (&tel_timer) tel_pend <= 4'd10;"),
    ("""				if (tel_pend == 4'd9) begin""",
     """				if (tel_pend == 4'd10) begin"""),
    ("""				end else if (tel_pend == 4'd8) begin
					ram_addr <= BASE_TEL + 25'd1;""",
     """				end else if (tel_pend == 4'd9) begin
					ram_addr <= BASE_TEL + 25'd1;"""),
    ("""				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd2;""",
     """				end else if (tel_pend == 4'd8) begin
					ram_addr <= BASE_TEL + 25'd2;"""),
    ("""				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd3;""",
     """				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd3;"""),
    ("""				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd4;""",
     """				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd4;"""),
    ("""				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd5;""",
     """				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd5;"""),
    ("""				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd6;""",
     """				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd6;"""),
    ("""				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd7;
					ram_din  <= tel_mdaddr;
				end else begin
					ram_addr <= BASE_TEL + 25'd8;
					ram_din  <= tel_trap;
				end""",
     """				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd7;
					ram_din  <= tel_mdaddr;
				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd8;
					ram_din  <= tel_trap;
				end else begin
					ram_addr <= BASE_TEL + 25'd9;
					ram_din  <= tel_cd;
				end"""),
])
