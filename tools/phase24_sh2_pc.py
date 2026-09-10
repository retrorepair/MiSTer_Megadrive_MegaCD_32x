#!/usr/bin/env python3
"""Expose both SH-2 program counters so a spinning 32X title can be located in its own ROM.

WHY
Doom CD32X Fusion comes up, writes about 0x12 words to the 32X frame buffer, and then never draws
again - with or without the disc - while the SH-2s keep executing (work-RAM reads and writes both
advancing) and the Mega CD sub-CPU runs healthily at ~2.4M PRG-RAM reads/s. Night Trap on the same
build runs perfectly, so the CD32X tower itself is sound. The SH-2s are WAITING on something rather
than deadlocked, and nothing measurable says what.

The SH-2 core already carries the answer: SH_core.sv:813 exposes PIPE.WB.PC through DBG_REGQ, but
only inside `ifdef DEBUG`, which is not set. This adds an unconditional PC output instead - it is a
existing register, so it costs routing and nothing else - and threads it to a telemetry beat. Sampling
it every few milliseconds over a spin loop gives the address range, which can then be disassembled
straight out of the Fusion ROM with tools/dis68k.py's SH-2 equivalent, or simply matched against the
ROM map.

Beat 4 at DDR3 0x30200020:
       [63:32] master SH-2 PC
       [31: 0] slave SH-2 PC

Usage: phase24_sh2_pc.py <core dir>"""
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


# ---------------------------------------------------------------- SH_core.sv
edit("rtl/SH/core/SH_core.sv", [
    # DBG_PC must sit OUTSIDE `ifdef DEBUG - ILI and DBG_REGQ are both inside it, and SH7604
    # connects DBG_PC unconditionally.
    ("\toutput            SLEEP\n\t\n`ifdef DEBUG",
     "\toutput            SLEEP,\n"
     "\n"
     "\t// Write-back stage PC, always available. DBG_REGQ already exposes this at DBG_REGN==5'h14\n"
     "\t// but only under `ifdef DEBUG; a spinning title has to be locatable without a rebuild of\n"
     "\t// the world, and PIPE.WB.PC is an existing register so this costs routing and nothing else.\n"
     "\toutput     [31:0] DBG_PC\n"
     "\t\n`ifdef DEBUG"),
    ("""	//Debug
`ifdef DEBUG""",
     """	assign DBG_PC = PIPE.WB.PC;

	//Debug
`ifdef DEBUG"""),
])

# ---------------------------------------------------------------- SH7604.sv
edit("rtl/SH/SH7604/SH7604.sv", [
    ("""`ifdef DEBUG
	                  ,
	input       [4:0] DBG_REGN,""",
     """	                  ,
	output     [31:0] DBG_PC
`ifdef DEBUG
	                  ,
	input       [4:0] DBG_REGN,"""),
    ("""		.SLEEP(SLEEP)
`ifdef DEBUG""",
     """		.SLEEP(SLEEP),
		.DBG_PC(DBG_PC)
`ifdef DEBUG"""),
])

# ---------------------------------------------------------------- 32X.sv
edit("rtl/S32X/32X.sv", [
    ("""	output     [23:0] DBG_CA
);""",
     """	output     [23:0] DBG_CA,
	output     [31:0] DBG_MSH_PC,		// tools/phase24_sh2_pc.py
	output     [31:0] DBG_SSH_PC
);"""),
    ("""		.MD(6'b001000)
	);""",
     """		.MD(6'b001000),
		.DBG_PC(DBG_MSH_PC)
	);"""),
    ("""		.MD(6'b101000)
	);""",
     """		.MD(6'b101000),
		.DBG_PC(DBG_SSH_PC)
	);"""),
])

# ---------------------------------------------------------------- MegaCD.sv
edit("MegaCD.sv", [
    ("""	.DBG_SECTOR_END(MCD_DBG_SECTOR_END),""",
     """	.DBG_SECTOR_END(MCD_DBG_SECTOR_END),"""),
    ("""wire [63:0] tel_sector = {tel_sec_end, tel_cdd_send, tel_dec_frame, tel_dec_mid};""",
     """wire [63:0] tel_sector = {tel_sec_end, tel_cdd_send, tel_dec_frame, tel_dec_mid};

// Both SH-2 program counters (tools/phase24_sh2_pc.py). Sampled over a spin loop these give the
// address range the title is stuck in, which can then be matched against its ROM.
wire [31:0] S32X_MSH_PC, S32X_SSH_PC;
wire [63:0] tel_sh2pc = {S32X_MSH_PC, S32X_SSH_PC};"""),
    ("""	.tel_sector(tel_sector)
);""",
     """	.tel_sector(tel_sector),
	.tel_sh2pc(tel_sh2pc)
);"""),
    ("""	.SH2_DIV2(status[2]),""",
     """	.SH2_DIV2(status[2]),
	.DBG_MSH_PC(S32X_MSH_PC),
	.DBG_SSH_PC(S32X_SSH_PC),"""),
])

# ---------------------------------------------------------------- s32x_ddr.sv: a fifth beat
edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_sector    // drive sector rate (tools/phase19_sector_rate.py)
);""",
     """	input      [63:0] tel_sector,   // drive sector rate (tools/phase19_sector_rate.py)
	input      [63:0] tel_sh2pc     // both SH-2 PCs (tools/phase24_sh2_pc.py)
);"""),
    ("reg   [2:0] tel_pend = 0;    // 4 = counters, 3 = audio, 2 = MCD bus, 1 = sector rate",
     "reg   [2:0] tel_pend = 0;    // 5 = counters, 4 = audio, 3 = MCD bus, 2 = sector rate, 1 = SH-2 PCs"),
    ("\t\tif (&tel_timer) tel_pend <= 3'd4;",
     "\t\tif (&tel_timer) tel_pend <= 3'd5;"),
    ("""				if (tel_pend == 3'd4) begin""",
     """				if (tel_pend == 3'd5) begin"""),
    ("""				end else if (tel_pend == 3'd3) begin
					ram_addr <= BASE_TEL + 25'd1;
					ram_din  <= tel_audio;
				end else if (tel_pend == 3'd2) begin
					ram_addr <= BASE_TEL + 25'd2;
					ram_din  <= tel_mcdbus;
				end else begin
					ram_addr <= BASE_TEL + 25'd3;
					ram_din  <= tel_sector;
				end""",
     """				end else if (tel_pend == 3'd4) begin
					ram_addr <= BASE_TEL + 25'd1;
					ram_din  <= tel_audio;
				end else if (tel_pend == 3'd3) begin
					ram_addr <= BASE_TEL + 25'd2;
					ram_din  <= tel_mcdbus;
				end else if (tel_pend == 3'd2) begin
					ram_addr <= BASE_TEL + 25'd3;
					ram_din  <= tel_sector;
				end else begin
					ram_addr <= BASE_TEL + 25'd4;
					ram_din  <= tel_sh2pc;
				end"""),
])
