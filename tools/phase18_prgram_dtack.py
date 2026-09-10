#!/usr/bin/env python3
"""Measure the Mega CD sub-CPU's PRG-RAM bus timing, and offer the reference core's early DTACK as a
runtime A/B.

WHY
The four remaining mcd-verificator failures (VAR TESTS 02, IRQ TEST 06, REG 8030 07, CDC FLAGS 40) are
all COUNTS THAT READ LOW, which is what a sub-CPU running slower than the real one produces. The b66
reference core passes three of the four with a CDC.vhd that is byte-identical to ours, so the difference
is not CD logic. Diffing its ASIC.vhd against ours leaves exactly one behavioural change, and its own
comment names our test:

    "The SDRAM controller has accepted the read: from here the data arrives in a fixed ~60 ns, so DTACK
     can go now. The 68000 latches data one clock (80 ns) after it samples DTACK; acknowledging only
     once the data was back cost the die-accurate CPU a wait state on nearly every PRG-RAM fetch
     (measured 93-105 ns AS to DTACK) where the real PRG-RAM answers with none (mcd-verificator VAR test)."

That change is NOT safe to copy blind into this core. It acknowledges the CPU when the SDRAM has merely
CAPTURED the request, leaving S68K_PRGRAM_DO stale until the data actually lands; sdram.sv serves five
ports at fixed priority with the Mega CD PRG-RAM on port 2, BELOW the cartridge port that the MD 68000
and both SH-2s share, so the "fixed ~60 ns" is not fixed here. The reference core has no 32X. Shipping
it unmeasured would repeat the /AS mistake, so this build measures first and switches second.

WHAT THIS ADDS
1. Telemetry beat 3 at DDR3 0x30200010: sub-CPU /AS-to-/DTACK latency for PRG-RAM reads.
       [63:56] min latency, clk_sys cycles (saturating)
       [55:48] max latency, clk_sys cycles (saturating)
       [47:32] reads that missed the no-wait-state deadline
       [31: 0] PRG-RAM reads timed
   The sub-CPU runs at 12.5 MHz = 4.2946 clk_sys per CPU clock. /AS falls at the start of S2 and
   /DTACK is sampled at the end of S4, so the gate array has 1.5 CPU clocks = 120 ns = 6.44 clk_sys
   to answer before the CPU inserts a wait state. Latency > 6 counts as slow.
2. OSD debug bit 28 ("MCD PRG DTACK: Data / Early"), default Data = today's behaviour. Early selects
   the reference core's timing so both can be run back to back on one bitstream.

Read with: python3 /media/fat/hpsmem.py read 30200010 8
Usage: phase18_prgram_dtack.py <core dir>"""
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


# ---------------------------------------------------------------- ASIC.vhd
edit("rtl/MCD/ASIC.vhd", [
    # entity: the A/B control
    ("""		PRG_RFS			: out std_logic;
		PRG_RDY			: in std_logic;""",
     """		PRG_RFS			: out std_logic;
		PRG_RDY			: in std_logic;
		DBG_EARLY_DTACK: in std_logic;		-- 1 = acknowledge the sub-CPU when the SDRAM accepts the
														-- request rather than when the data is back (reference
														-- core timing). See tools/phase18_prgram_dtack.py."""),
    # writes: post them
    ("""								PRG_RAM_WRL <= not S68K_LDS_N and not S68K_RNW;
								PRG_RAM_WRH <= not S68K_UDS_N and not S68K_RNW;
								PRG_RAM_RD <= S68K_RNW;
								-- (fx68k sub-CPU: writes are acknowledged in PRS_WRITE, reads in PRS_READ, as upstream)
								PRSS <= PRS_WAIT;""",
     """								PRG_RAM_WRL <= not S68K_LDS_N and not S68K_RNW;
								PRG_RAM_WRH <= not S68K_UDS_N and not S68K_RNW;
								PRG_RAM_RD <= S68K_RNW;
								-- Writes are posted when DBG_EARLY_DTACK is set: address and data are latched
								-- here, so the CPU can be acknowledged at once (real PRG-RAM takes writes
								-- without wait states); the next PRG-RAM access still waits for this one to
								-- reach the SDRAM controller. Default is upstream: acknowledge in PRS_WRITE.
								if DBG_EARLY_DTACK = '1' and S68K_RNW = '0' then
									S68K_PRGRAM_DTACK_N <= '0';
								end if;
								PRSS <= PRS_WAIT;"""),
    # reads: acknowledge on acceptance
    ("""					when PRS_WAIT =>
						if PRG_RDY = '0' then
							if PRG_RAM_RD = '1' then
								PRSS <= PRS_READ;
							else
								PRSS <= PRS_WRITE;
							end if;
						end if;""",
     """					when PRS_WAIT =>
						if PRG_RDY = '0' then
							-- The SDRAM controller has accepted the request. With DBG_EARLY_DTACK the CPU is
							-- acknowledged here and latches the data one clock later, which is what the real
							-- PRG-RAM does; it relies on the read completing inside that clock, and on this
							-- core the port sits below the cartridge port so that is not guaranteed. Measured
							-- by the beat-3 telemetry before it is made the default.
							if DBG_EARLY_DTACK = '1' and PRG_RAM_RD = '1' then
								S68K_PRGRAM_DTACK_N <= '0';
							end if;
							if PRG_RAM_RD = '1' then
								PRSS <= PRS_READ;
							else
								PRSS <= PRS_WRITE;
							end if;
						end if;"""),
])

# ---------------------------------------------------------------- MCD.vhd
edit("rtl/MCD/MCD.vhd", [
    ("""		PRG_RDY			: in std_logic;""",
     """		PRG_RDY			: in std_logic;
		DBG_EARLY_DTACK: in std_logic := '0';"""),
    ("""		PRG_RDY  		=> PRG_RDY,""",
     """		PRG_RDY  		=> PRG_RDY,
		DBG_EARLY_DTACK => DBG_EARLY_DTACK,"""),
])

# ---------------------------------------------------------------- MegaCD.sv
edit("MegaCD.sv", [
    # OSD entry next to the other MCD debug switch
    ('\t"H2O[39],MCD /AS,68000,Bus;",',
     '\t"H2O[39],MCD /AS,68000,Bus;",\n\t"H2O[28],MCD PRG DTACK,Data,Early;",'),
    # feed the A/B bit and take the debug outputs
    ("""	.PRG_OE_N(MCD_PRG_OE_N),
	.PRG_RDY(~MCD_PRG_BUSY),""",
     """	.PRG_OE_N(MCD_PRG_OE_N),
	.PRG_RDY(~MCD_PRG_BUSY),
	.DBG_EARLY_DTACK(status[28] & dbg_menu),

	.DBG_S68K_AS_N(MCD_DBG_AS_N),
	.DBG_S68K_DTACK_N(MCD_DBG_DTACK_N),
	.DBG_S68K_RNW(MCD_DBG_RNW),
	.DBG_S68K_A(MCD_DBG_A),"""),
    # the measurement itself, next to the audio telemetry
    ("""wire [63:0] tel_audio = {tel_pk_gen, tel_pk_mcd, tel_pk_pwm, tel_pk_out, tel_aud_ce};""",
     """wire [63:0] tel_audio = {tel_pk_gen, tel_pk_mcd, tel_pk_pwm, tel_pk_out, tel_aud_ce};

// Sub-CPU PRG-RAM bus timing (tools/phase18_prgram_dtack.py). The sub-CPU runs at 12.5 MHz, so one CPU
// clock is 4.2946 clk_sys. /AS falls at the start of S2 and /DTACK is sampled at the end of S4: the gate
// array has 1.5 CPU clocks = 120 ns = 6.44 clk_sys to answer, or the CPU inserts a wait state. Counting
// the reads that miss that deadline says whether the sub-CPU really is running slow, which is what all
// four remaining verificator failures look like.
wire        MCD_DBG_AS_N, MCD_DBG_DTACK_N, MCD_DBG_RNW;
wire [23:0] MCD_DBG_A;

localparam [7:0] DTACK_DEADLINE = 8'd6;

reg         dbg_as_d = 1, dbg_dtack_d = 1;
reg   [7:0] dbg_lat;
reg         dbg_arm;
reg   [7:0] tel_lat_min, tel_lat_max;
reg  [15:0] tel_lat_slow;
reg  [31:0] tel_lat_n;

always @(posedge clk_sys) begin
	if (reset) begin
		dbg_as_d <= 1; dbg_dtack_d <= 1; dbg_lat <= 0; dbg_arm <= 0;
		tel_lat_min <= 8'hFF; tel_lat_max <= 0; tel_lat_slow <= 0; tel_lat_n <= 0;
	end
	else begin
		dbg_as_d    <= MCD_DBG_AS_N;
		dbg_dtack_d <= MCD_DBG_DTACK_N;

		if (dbg_as_d & ~MCD_DBG_AS_N) begin
			// /AS falling. Time it only if it is a sub-CPU PRG-RAM read: PRG-RAM is $000000-$07FFFF
			// on the sub side, and a write is acknowledged by a different path.
			dbg_lat <= 0;
			dbg_arm <= MCD_DBG_RNW & ~|MCD_DBG_A[23:19];
		end
		else if (~MCD_DBG_AS_N && ~&dbg_lat) dbg_lat <= dbg_lat + 8'd1;

		if (dbg_arm & dbg_dtack_d & ~MCD_DBG_DTACK_N) begin
			dbg_arm      <= 0;
			tel_lat_n    <= tel_lat_n + 32'd1;
			if (dbg_lat > DTACK_DEADLINE && ~&tel_lat_slow) tel_lat_slow <= tel_lat_slow + 16'd1;
			if (dbg_lat < tel_lat_min) tel_lat_min <= dbg_lat;
			if (dbg_lat > tel_lat_max) tel_lat_max <= dbg_lat;
		end
	end
end
wire [63:0] tel_mcdbus = {tel_lat_min, tel_lat_max, tel_lat_slow, tel_lat_n};"""),
    # hand it to the telemetry writer
    ("""	.tel_audio(tel_audio)
);""",
     """	.tel_audio(tel_audio),
	.tel_mcdbus(tel_mcdbus)
);"""),
])

# ---------------------------------------------------------------- s32x_ddr.sv
edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_audio     // audio peaks + sample-enable count (tools/phase3_audio_probe.py)
);""",
     """	input      [63:0] tel_audio,    // audio peaks + sample-enable count (tools/phase3_audio_probe.py)
	input      [63:0] tel_mcdbus    // sub-CPU PRG-RAM bus timing (tools/phase18_prgram_dtack.py)
);"""),
    ("localparam        TELEMETRY = 0;\t// release: telemetry compiled out. Set to 1 for the DDR3 debug beats",
     "localparam        TELEMETRY = 1;\t// release: telemetry compiled out. Set to 1 for the DDR3 debug beats"),
    ("reg   [1:0] tel_pend = 0;    // 2 = counters beat, 1 = audio beat",
     "reg   [1:0] tel_pend = 0;    // 3 = counters beat, 2 = audio beat, 1 = MCD bus beat"),
    ("\t\tif (&tel_timer) tel_pend <= 2'd2;",
     "\t\tif (&tel_timer) tel_pend <= 2'd3;"),
    ("""				if (tel_pend == 2'd2) begin
					tel_seq  <= tel_seq + 1'd1;
					ram_addr <= BASE_TEL;
					ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
				end else begin
					ram_addr <= BASE_TEL + 25'd1;
					ram_din  <= tel_audio;
				end""",
     """				if (tel_pend == 2'd3) begin
					tel_seq  <= tel_seq + 1'd1;
					ram_addr <= BASE_TEL;
					ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
				end else if (tel_pend == 2'd2) begin
					ram_addr <= BASE_TEL + 25'd1;
					ram_din  <= tel_audio;
				end else begin
					ram_addr <= BASE_TEL + 25'd2;
					ram_din  <= tel_mcdbus;
				end"""),
])
