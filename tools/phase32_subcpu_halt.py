#!/usr/bin/env python3
"""Find out why the Mega CD sub-CPU stops dead during Doom CD32X Fusion.

WHY - measured on r17, with Fusion running:

    subCPU PRG reads  4945543  (+0) (+0) (+0) (+0) (+0)   frozen over 6 s
    CFM=00 CFS=00     comm flags idle, neither side moving
    SECTOR_END  34    static - no sectors
    CDD_SEND   269    static - the gate array has stopped asking the drive, i.e. HOCK = 0

A 68000 fetches every instruction from memory, so zero PRG-RAM reads means the sub-CPU is not
executing at all. It ran earlier in the boot (the counter got to ~4.9M) and then stopped. Everything
downstream follows: no sectors, so play_cd_roq_file never completes, so COMM0 bit 0 is never set, so
the 68000 spins at $884C08 and the master SH-2 waits, and nothing is drawn.

Three ways a sub-CPU stops, and this tells them apart:
  * held by the gate array - the 68000 asserted SBRQ (bus request) or SRES (reset) via $A12001 and
    never released it. Fusion does exactly this to upload its program (src-md/scd.c) and again for
    later transfers, so a missed release would strand it.
  * stalled on a bus cycle whose DTACK never arrives - /AS low, DTACK high, address static. This is
    the same class of fault as the RS_MD_WAIT deadlock already fixed on the MD side.
  * executing elsewhere (e.g. Word RAM) - /AS still toggling, address outside PRG-RAM.

Beat 10 at DDR3 0x30200050:
       [63:40] sub-CPU address bus (A23:A1 << 1), live
       [39:32] {SRES, SBRQ, AS_N, DTACK_N, RNW, 3'b0}
       [31: 0] count of sub-CPU /AS falling edges - zero movement here proves it is not running

Readings:
  AS edges static, SBRQ=1  -> the 68000 is holding the bus and never gave it back
  AS edges static, SRES=0  -> it is being held in reset
  AS edges static, AS_N=0, DTACK_N=1 -> stalled mid-cycle waiting for an acknowledge: the address
                                        field says exactly which access wedged
  AS edges moving          -> it IS running, just not out of PRG-RAM; follow the address

Usage: phase32_subcpu_halt.py <core dir>"""
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
    ("""		DBG_CFM			: out std_logic_vector(7 downto 0);	-- tools/phase31_cd_handshake.py""",
     """		DBG_SRES			: out std_logic;						-- tools/phase32_subcpu_halt.py
		DBG_SBRQ			: out std_logic;
		DBG_CFM			: out std_logic_vector(7 downto 0);	-- tools/phase31_cd_handshake.py"""),
    ("""	-- the gate array's communication flags, $A1200E / $A1200F""",
     """	-- sub-CPU reset and bus request, $A12001 bits 0 and 1
	DBG_SRES <= SRES;
	DBG_SBRQ <= SBRQ;

	-- the gate array's communication flags, $A1200E / $A1200F"""),
])

edit("rtl/MCD/MCD.vhd", [
    ("""		DBG_CFM			: out std_logic_vector(7 downto 0);	-- tools/phase31_cd_handshake.py""",
     """		DBG_SRES			: out std_logic;						-- tools/phase32_subcpu_halt.py
		DBG_SBRQ			: out std_logic;
		DBG_CFM			: out std_logic_vector(7 downto 0);	-- tools/phase31_cd_handshake.py"""),
    ("""		DBG_CFM         => DBG_CFM,""",
     """		DBG_SRES        => DBG_SRES,
		DBG_SBRQ        => DBG_SBRQ,
		DBG_CFM         => DBG_CFM,"""),
])

edit("MegaCD.sv", [
    ("""	.DBG_CFM(MCD_DBG_CFM),""",
     """	.DBG_SRES(MCD_DBG_SRES),
	.DBG_SBRQ(MCD_DBG_SBRQ),
	.DBG_CFM(MCD_DBG_CFM),"""),
    ("""wire [63:0] tel_cd = {MCD_DBG_CFM, MCD_DBG_CFS, tel_cfs_chg, tel_cfm_chg, 16'h0000};""",
     """wire [63:0] tel_cd = {MCD_DBG_CFM, MCD_DBG_CFS, tel_cfs_chg, tel_cfm_chg, 16'h0000};

// Why the sub-CPU stopped (tools/phase32_subcpu_halt.py). Its address bus and strobes are already
// brought out for the PRG-RAM latency probe; this adds the gate array's hold signals and a bus-cycle
// count, which separates "held by the 68000" from "stalled waiting for an acknowledge".
wire        MCD_DBG_SRES, MCD_DBG_SBRQ;
reg  [31:0] tel_sub_cycles;
reg         sub_as_d = 1;
always @(posedge clk_sys) begin
	if (reset) begin
		tel_sub_cycles <= 0; sub_as_d <= 1;
	end
	else begin
		sub_as_d <= MCD_DBG_AS_N;
		if (sub_as_d & ~MCD_DBG_AS_N) tel_sub_cycles <= tel_sub_cycles + 32'd1;
	end
end
wire [63:0] tel_sub = {MCD_DBG_A[23:1], 1'b0,
                       MCD_DBG_SRES, MCD_DBG_SBRQ, MCD_DBG_AS_N, MCD_DBG_DTACK_N, MCD_DBG_RNW, 3'b000,
                       tel_sub_cycles};"""),
    ("""	.tel_cd(tel_cd)
);""",
     """	.tel_cd(tel_cd),
	.tel_sub(tel_sub)
);"""),
])

edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_cd        // Mega CD comm flags (tools/phase31_cd_handshake.py)
);""",
     """	input      [63:0] tel_cd,       // Mega CD comm flags (tools/phase31_cd_handshake.py)
	input      [63:0] tel_sub       // sub-CPU halt state (tools/phase32_subcpu_halt.py)
);"""),
    ("reg   [3:0] tel_pend = 0;    // 10=counters 9=audio 8=MCDbus 7=sector 6=SH2PC 5=MD 4=comm 3=mdaddr 2=trap 1=cd",
     "reg   [3:0] tel_pend = 0;    // 11=counters ... 3=trap 2=cd 1=sub"),
    ("\t\tif (&tel_timer) tel_pend <= 4'd10;",
     "\t\tif (&tel_timer) tel_pend <= 4'd11;"),
    ("""				if (tel_pend == 4'd10) begin""",
     """				if (tel_pend == 4'd11) begin"""),
    ("""				end else if (tel_pend == 4'd9) begin
					ram_addr <= BASE_TEL + 25'd1;""",
     """				end else if (tel_pend == 4'd10) begin
					ram_addr <= BASE_TEL + 25'd1;"""),
    ("""				end else if (tel_pend == 4'd8) begin
					ram_addr <= BASE_TEL + 25'd2;""",
     """				end else if (tel_pend == 4'd9) begin
					ram_addr <= BASE_TEL + 25'd2;"""),
    ("""				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd3;""",
     """				end else if (tel_pend == 4'd8) begin
					ram_addr <= BASE_TEL + 25'd3;"""),
    ("""				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd4;""",
     """				end else if (tel_pend == 4'd7) begin
					ram_addr <= BASE_TEL + 25'd4;"""),
    ("""				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd5;""",
     """				end else if (tel_pend == 4'd6) begin
					ram_addr <= BASE_TEL + 25'd5;"""),
    ("""				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd6;""",
     """				end else if (tel_pend == 4'd5) begin
					ram_addr <= BASE_TEL + 25'd6;"""),
    ("""				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd7;""",
     """				end else if (tel_pend == 4'd4) begin
					ram_addr <= BASE_TEL + 25'd7;"""),
    ("""				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd8;
					ram_din  <= tel_trap;
				end else begin
					ram_addr <= BASE_TEL + 25'd9;
					ram_din  <= tel_cd;
				end""",
     """				end else if (tel_pend == 4'd3) begin
					ram_addr <= BASE_TEL + 25'd8;
					ram_din  <= tel_trap;
				end else if (tel_pend == 4'd2) begin
					ram_addr <= BASE_TEL + 25'd9;
					ram_din  <= tel_cd;
				end else begin
					ram_addr <= BASE_TEL + 25'd10;
					ram_din  <= tel_sub;
				end"""),
])
