#!/usr/bin/env python3
"""Who owns the 32X frame buffer, and who is being refused? (Doom CD32X Fusion, OPEN #1)

WHY
The hang chain is established: the SH-2 reads *(int*)0x24000200 as 0xFFFFFFFF, numtextures = -1,
memset never terminates. That word is Mars_GetCDFileBuffer(), and the DDR3 content of the buffer on
a failing boot is 0xFF over 88% of a 16 KB sample - pristine memory. But BOTH sides write it in
every CD read:

    SH-2 (marshw.c Mars_ReadCDFile): word-clears the buffer to 0, then COMM0 = 0x2800
    MD   (crt0.s read_cd_file):      eor #0x8000,A15100 (FM->0), writes the data, or #0x8000 (FM->1)

so a buffer that is neither 0 nor CD data means NEITHER write landed. The 32X FM bit is the only
thing that can refuse both: IF.sv:1000 takes an MD frame-buffer access only when FM==0 and
IF.sv:1028 takes an SH-2 one only when FM==1. A refused MD access is acked and dropped; a refused
SH-2 access is dropped with no wait and no ack at all. If FM is 0 when the SH-2 clears, its writes
vanish - and read_cd_file's EOR then flips FM to 1, so the MD's data writes vanish too. One wrong
bit, both writers silenced, buffer left pristine.

This probe does not change behaviour. It counts the refusals and records who last wrote FM, so a
failing boot can be told apart from a working one by measurement rather than by argument.

DBG_INT (IF.sv, unused since phase34) is repurposed and lands in telemetry beat 12
(0x30200060, high 32 bits; the low half keeps phase51's FS-at-access word):

    [31:24] SH-2 frame-buffer WRITES refused because FM==0   (saturating)
    [23:16] MD   frame-buffer WRITES refused because FM==1   (saturating)
    [15:12] SH-2 frame-buffer READS  refused                 (saturating 15)
    [11: 8] MD   frame-buffer READS  refused                 (saturating 15)
    [ 7]    FM now
    [ 6]    last write to FM came from the SH-2 (1) or the MD (0)
    [ 5]    value the SH-2 last wrote to FM
    [ 4]    value the MD last wrote to FM
    [ 3: 0] FM transitions (saturating 15)

Usage: phase53_fm_probe.py <core dir>"""
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
    # --- who writes FM: the MD through $A15100
    ("""						6'h00: begin
							if (!LWR_V) ADCR[ 7:0] <= VDI_SYNC[ 7:0] & ADCR_MASK[ 7:0];
							if (!UWR_V) ADCR[15:8] <= VDI_SYNC[15:8] & ADCR_MASK[15:8];
						end""",
     """						6'h00: begin
							if (!LWR_V) ADCR[ 7:0] <= VDI_SYNC[ 7:0] & ADCR_MASK[ 7:0];
							if (!UWR_V) ADCR[15:8] <= VDI_SYNC[15:8] & ADCR_MASK[15:8];
							if (!UWR_V) begin DBG_FM_WHO <= 0; DBG_FM_MDV <= VDI_SYNC[15]; end	// phase53
						end"""),

    # --- who writes FM: an SH-2 through $20004000
    ("""							if (!SHDQMLU_N) ADCR.FM <= SHDI[15];""",
     """							if (!SHDQMLU_N) ADCR.FM <= SHDI[15];
							if (!SHDQMLU_N) begin DBG_FM_WHO <= 1; DBG_FM_SHV <= SHDI[15]; end	// phase53"""),

    # --- MD frame-buffer access refused because the SH-2s hold the buffer
    ("""				end else begin
					VDP_DTACK_N <= 0;
				end
			end else if (MD_VDP_SEL && MD_VDP_ACCESS) begin""",
     """				end else begin
					// FM == 1: the SH-2s own the frame buffer, so this MD access is acked and dropped.
					// A dropped MD write is how read_cd_file's CD data silently fails to arrive (phase53).
					if (MD_VDPDRAM_SEL) begin
						if (LWR_F || UWR_F) begin if (~&DBG_MD_WDENY) DBG_MD_WDENY <= DBG_MD_WDENY + 8'd1; end
						else                begin if (~&DBG_MD_RDENY) DBG_MD_RDENY <= DBG_MD_RDENY + 4'd1; end
					end
					VDP_DTACK_N <= 0;
				end
			end else if (MD_VDP_SEL && MD_VDP_ACCESS) begin"""),

    # --- SH-2 frame-buffer access refused because the 68000 holds the buffer
    ("""			if (SH_VDP_SEL && ADCR.FM && !SHBS_N && CE_F) begin
				SH_VDP_WAIT <= 1;""",
     """			// FM == 0: the 68000 owns the frame buffer, so this SH-2 access does nothing at all -
			// no wait, no ack, the write simply evaporates. Count it (phase53).
			if (SH_VDPDRAM_SEL && !ADCR.FM && !SHBS_N && CE_F) begin
				if (!SHRD_WR_N) begin if (~&DBG_SH_WDENY) DBG_SH_WDENY <= DBG_SH_WDENY + 8'd1; end
				else            begin if (~&DBG_SH_RDENY) DBG_SH_RDENY <= DBG_SH_RDENY + 4'd1; end
			end
			if (SH_VDP_SEL && ADCR.FM && !SHBS_N && CE_F) begin
				SH_VDP_WAIT <= 1;"""),

    # --- reset the counters with the block they live in
    ("""			VDP_DTACK_N <= 1;
			MD_VDP_ACCESS <= 0;
			SH_VDP_WAIT <= 0;
			SH_VDP_ACCESS <= 0;""",
     """			VDP_DTACK_N <= 1;
			MD_VDP_ACCESS <= 0;
			SH_VDP_WAIT <= 0;
			SH_VDP_ACCESS <= 0;
			DBG_SH_WDENY <= '0; DBG_MD_WDENY <= '0; DBG_SH_RDENY <= '0; DBG_MD_RDENY <= '0;	// phase53"""),

    # --- the probe word itself
    ("""	assign DBG_INT = {ICR, IMMR};""",
     """	// FM ownership probe (tools/phase53_fm_probe.py). DBG_INT has been unused since phase34.
	bit [7:0] DBG_SH_WDENY, DBG_MD_WDENY;
	bit [3:0] DBG_SH_RDENY, DBG_MD_RDENY, DBG_FM_CHG;
	bit       DBG_FM_WHO, DBG_FM_SHV, DBG_FM_MDV, DBG_FM_D;
	always @(posedge CLK or negedge RST_N) begin
		if (!RST_N) begin DBG_FM_D <= 0; DBG_FM_CHG <= '0; end
		else begin
			DBG_FM_D <= ADCR.FM;
			if (ADCR.FM != DBG_FM_D && ~&DBG_FM_CHG) DBG_FM_CHG <= DBG_FM_CHG + 4'd1;
		end
	end
	assign DBG_INT = {DBG_SH_WDENY, DBG_MD_WDENY, DBG_SH_RDENY, DBG_MD_RDENY,
	                  ADCR.FM, DBG_FM_WHO, DBG_FM_SHV, DBG_FM_MDV, DBG_FM_CHG};
	wire unused_icr_immr = |{ICR, IMMR};"""),
])

edit("MegaCD.sv", [
    ("""wire [63:0] tel_int = {ms_from3, S32X_DBG_FB};""",
     """wire [63:0] tel_int = {S32X_INT, S32X_DBG_FB};	// phase53: FM ownership in the high half"""),
    ("""wire unused_ms4 = |ms_from4;""",
     """wire unused_ms4 = |{ms_from4, ms_from3};"""),
])
