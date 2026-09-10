#!/usr/bin/env python3
"""Measure the Mega CD drive's real sector rate against the gate array's 75 Hz frame request.

WHY
mcd-verificator CDC FLAGS sub-tests 0x40/0x41 time the decoder interrupt flag over one drive
period by polling IFSTAT bit 5 (DECI) through the main<->sub RPC:

    d4 = polls while DECI asserted   expected 48-50
    d5 = polls while DECI cleared    expected 71-73      49/121 = 40.5%

This core reports d4 = 87, d5 = 69 (measured by widening the d4 bound, tools/verif_patch_cdcflags.py);
the b66 reference passes the same patched ROM on the same disc. The duty cycle - 87/156 = 55.8% against
40.5% - is independent of how fast the poll loop runs, so it is a real waveform error.

CDC.vhd asserts DECI and pulses SECTOR_END (which zeroes FRAME_CNT) at the last word of every sector,
and DEC_MID clears DECI 40% of a frame later. So with sectors every P:

    cleared phase  = 13.33 - 5.33 = 8.0 ms   (fixed)
    asserted phase = (P - 13.33) + 5.33 = P - 8.0

The model reproduces b66 exactly (40.5% -> P = 13.45 ms) and gives P ~ 18 ms for this core, i.e. sectors
arriving nearer 55 Hz than 75 Hz. CDC.vhd is byte-identical to b66's, ASIC.vhd differs only in the
PRG-RAM DTACK hunks, CLK_12M_F/CDD_FRAME_CNT are identical, and both top levels feed the CDC through the
same hps_ext path - so the pacing is right and the sectors themselves are late. That has to be measured
rather than argued.

WHAT THIS ADDS
Telemetry beat 4 at DDR3 0x30200018, four free-running 16-bit counters (wrap at 65536/75 = 874 s):
       [63:48] SECTOR_END  - complete sectors decoded by the CDC
       [47:32] CDD_SEND    - drive frames requested by the gate array (must be 75/s)
       [31:16] DEC_FRAME   - free-running 75 Hz frame boundaries
       [15: 0] DEC_MID     - the 40% auto-clear pulses
Read two samples a known time apart and divide. The three outcomes are distinct:
  * CDD_SEND 75/s and SECTOR_END 75/s   -> pacing fine, the fault is elsewhere in the DECI logic
  * CDD_SEND 75/s and SECTOR_END ~55/s  -> sectors are arriving late or short (HPS delivery)
  * CDD_SEND ~55/s                      -> the gate array itself is requesting slowly

Read with: python3 /media/fat/hpsmem.py read 30200018 8
Usage: phase19_sector_rate.py <core dir>"""
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


# ---------------------------------------------------------------- CDC.vhd: export the three pulses
edit("rtl/MCD/CDC.vhd", [
    ("""		RAM_DO		: out std_logic_vector(15 downto 0);
		RAM_WE		: out std_logic
	);
end CDC;""",
     """		RAM_DO		: out std_logic_vector(15 downto 0);
		RAM_WE		: out std_logic;

		-- single-cycle pulses, counted in the top level (tools/phase19_sector_rate.py)
		DBG_SECTOR_END	: out std_logic;
		DBG_DEC_FRAME	: out std_logic;
		DBG_DEC_MID		: out std_logic
	);
end CDC;"""),
    ("""	RAM_WE <= DEC_WR and DEC_WR_EN and CTRL0(DECEN);""",
     """	RAM_WE <= DEC_WR and DEC_WR_EN and CTRL0(DECEN);

	DBG_SECTOR_END <= SECTOR_END;
	DBG_DEC_FRAME  <= DEC_FRAME;
	DBG_DEC_MID    <= DEC_MID;"""),
])

# ---------------------------------------------------------------- MCD.vhd: pass them up
edit("rtl/MCD/MCD.vhd", [
    ("""		DBG_EARLY_DTACK: in std_logic := '0';""",
     """		DBG_EARLY_DTACK: in std_logic := '0';
		DBG_SECTOR_END	: out std_logic;
		DBG_DEC_FRAME	: out std_logic;
		DBG_DEC_MID		: out std_logic;"""),
    ("""	CDC : entity work.CDC
	port map(
		CLK   		=> CLK,""",
     """	CDC : entity work.CDC
	port map(
		DBG_SECTOR_END => DBG_SECTOR_END,
		DBG_DEC_FRAME  => DBG_DEC_FRAME,
		DBG_DEC_MID    => DBG_DEC_MID,
		CLK   		=> CLK,"""),
])

# ---------------------------------------------------------------- MegaCD.sv
edit("MegaCD.sv", [
    ("""	.DBG_S68K_AS_N(MCD_DBG_AS_N),""",
     """	.DBG_SECTOR_END(MCD_DBG_SECTOR_END),
	.DBG_DEC_FRAME(MCD_DBG_DEC_FRAME),
	.DBG_DEC_MID(MCD_DBG_DEC_MID),

	.DBG_S68K_AS_N(MCD_DBG_AS_N),"""),
    ("""wire [63:0] tel_mcdbus = {tel_lat_min, tel_lat_max, tel_lat_slow, tel_lat_n};""",
     """wire [63:0] tel_mcdbus = {tel_lat_min, tel_lat_max, tel_lat_slow, tel_lat_n};

// Drive sector rate against the gate array's 75 Hz frame request (tools/phase19_sector_rate.py).
// CDD_SEND is the gate array asking the drive for a frame; SECTOR_END is the CDC finishing a whole
// 2352-byte sector. On hardware both are 75/s. Counting them separately says whether the request
// pacing or the delivery is what stretches the decoder flag's period to ~18 ms.
wire MCD_DBG_SECTOR_END, MCD_DBG_DEC_FRAME, MCD_DBG_DEC_MID;

reg [15:0] tel_sec_end, tel_cdd_send, tel_dec_frame, tel_dec_mid;
reg        tel_cdd_send_d;
always @(posedge clk_sys) begin
	if (reset) begin
		tel_sec_end <= 0; tel_cdd_send <= 0; tel_dec_frame <= 0; tel_dec_mid <= 0;
		tel_cdd_send_d <= 0;
	end
	else begin
		tel_cdd_send_d <= scd_cdd_send;
		if (MCD_DBG_SECTOR_END)              tel_sec_end   <= tel_sec_end   + 16'd1;
		if (scd_cdd_send & ~tel_cdd_send_d)  tel_cdd_send  <= tel_cdd_send  + 16'd1;
		if (MCD_DBG_DEC_FRAME)               tel_dec_frame <= tel_dec_frame + 16'd1;
		if (MCD_DBG_DEC_MID)                 tel_dec_mid   <= tel_dec_mid   + 16'd1;
	end
end
wire [63:0] tel_sector = {tel_sec_end, tel_cdd_send, tel_dec_frame, tel_dec_mid};"""),
    ("""	.tel_mcdbus(tel_mcdbus)
);""",
     """	.tel_mcdbus(tel_mcdbus),
	.tel_sector(tel_sector)
);"""),
])

# ---------------------------------------------------------------- s32x_ddr.sv: a fourth beat
edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_mcdbus    // sub-CPU PRG-RAM bus timing (tools/phase18_prgram_dtack.py)
);""",
     """	input      [63:0] tel_mcdbus,   // sub-CPU PRG-RAM bus timing (tools/phase18_prgram_dtack.py)
	input      [63:0] tel_sector    // drive sector rate (tools/phase19_sector_rate.py)
);"""),
    ("reg   [1:0] tel_pend = 0;    // 3 = counters beat, 2 = audio beat, 1 = MCD bus beat",
     "reg   [2:0] tel_pend = 0;    // 4 = counters, 3 = audio, 2 = MCD bus, 1 = sector rate"),
    ("\t\tif (&tel_timer) tel_pend <= 2'd3;",
     "\t\tif (&tel_timer) tel_pend <= 3'd4;"),
    ("""				if (tel_pend == 2'd3) begin
					tel_seq  <= tel_seq + 1'd1;
					ram_addr <= BASE_TEL;
					ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
				end else if (tel_pend == 2'd2) begin
					ram_addr <= BASE_TEL + 25'd1;
					ram_din  <= tel_audio;
				end else begin
					ram_addr <= BASE_TEL + 25'd2;
					ram_din  <= tel_mcdbus;
				end""",
     """				if (tel_pend == 3'd4) begin
					tel_seq  <= tel_seq + 1'd1;
					ram_addr <= BASE_TEL;
					ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
				end else if (tel_pend == 3'd3) begin
					ram_addr <= BASE_TEL + 25'd1;
					ram_din  <= tel_audio;
				end else if (tel_pend == 3'd2) begin
					ram_addr <= BASE_TEL + 25'd2;
					ram_din  <= tel_mcdbus;
				end else begin
					ram_addr <= BASE_TEL + 25'd3;
					ram_din  <= tel_sector;
				end"""),
])
