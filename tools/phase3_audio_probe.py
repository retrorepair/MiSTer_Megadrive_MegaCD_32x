#!/usr/bin/env python3
"""Add audio telemetry (the last unverified subsystem) and restore the Mega CD's /FDC DTACK wait.

Audio: a second telemetry beat at DDR3 0x30200008 carrying the peak level seen on each of the four
points in the mix, plus a count of audio sample enables so a dead clock is distinguishable from silence:
    [63:56] peak |console mix|  (FM + PSG + EXT channel, gen's DAC output)
    [55:48] peak |Mega CD|      (PCM + CDDA)
    [47:40] peak |32X PWM|
    [39:32] peak |final mix|    (what reaches AUDIO_L)
    [31: 0] audio sample-enable count
Read with: python3 /media/fat/hpsmem.py read 30200008 8
Peaks are the top 8 bits of the absolute value and are sticky, so a title only has to make a sound once.

/FDC: the Mega CD gate array answers $A12000 with its own /DTACK and srg320's older Mega CD gen waited
for it; the S32X-revision arbiter auto-terminates. Games boot either way because the BIOS is forgiving,
but mcd-verificator hangs at "System init..." polling those registers raw. The audit measured the
difference as one MCLK, so waiting is what the hardware does.
Usage: phase3_audio_probe.py <core dir>"""
import sys, os
d = sys.argv[1]

def edit(rel, pairs):
    p = os.path.join(d, rel)
    s = open(p, encoding="utf-8", errors="replace").read()
    for old, new in pairs:
        assert old in s, rel + ": anchor missing: " + old[:70]
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(s)
    print(rel, "ok")

# --- audio peak capture in the top, fed to the telemetry writer
edit("MegaCD.sv", [
("""audio_fix #(250) audio_fix // MCLK/504 in lpf, so choose half to get in the middle of sample period""",
 """// Audio telemetry: sticky peak of each point in the mix plus a sample-enable count, so a silent tier
// can be told apart from a stopped audio clock. See tools/phase3_audio_probe.py.
function [7:0] peak8(input [15:0] v);
	reg [15:0] a;
	begin
		a = v[15] ? (~v + 16'd1) : v;
		peak8 = a[15:8];
	end
endfunction
reg  [7:0] tel_pk_gen, tel_pk_mcd, tel_pk_pwm, tel_pk_out;
reg [31:0] tel_aud_ce;
always @(posedge clk_sys) begin
	if (reset) begin
		tel_pk_gen <= 0; tel_pk_mcd <= 0; tel_pk_pwm <= 0; tel_pk_out <= 0; tel_aud_ce <= 0;
	end
	else begin
		if (peak8(GEN_AUDL)   > tel_pk_gen) tel_pk_gen <= peak8(GEN_AUDL);
		if (peak8(mcd_l)      > tel_pk_mcd) tel_pk_mcd <= peak8(mcd_l);
		if (peak8(S32X_PWM_L) > tel_pk_pwm) tel_pk_pwm <= peak8(S32X_PWM_L);
		if (peak8(aud_l)      > tel_pk_out) tel_pk_out <= peak8(aud_l);
		if (GEN_CE) tel_aud_ce <= tel_aud_ce + 1'd1;
	end
end
wire [63:0] tel_audio = {tel_pk_gen, tel_pk_mcd, tel_pk_pwm, tel_pk_out, tel_aud_ce};

audio_fix #(250) audio_fix // MCLK/504 in lpf, so choose half to get in the middle of sample period"""),
("	.lb_addr(S32X_LB_ADDR),\n	.lb_q(S32X_LB_Q)\n);",
 "	.lb_addr(S32X_LB_ADDR),\n	.lb_q(S32X_LB_Q),\n\n	.tel_audio(tel_audio)\n);"),
])

# --- second telemetry beat
edit("rtl/s32x_ddr.sv", [
("	output     [15:0] lb_q          // registered: valid the clock after lb_addr\n);",
 "	output     [15:0] lb_q,         // registered: valid the clock after lb_addr\n\n	input      [63:0] tel_audio     // audio peaks + sample-enable count (tools/phase3_audio_probe.py)\n);"),
("reg         tel_pend = 0;", "reg   [1:0] tel_pend = 0;    // 2 = counters beat, 1 = audio beat"),
("		if (&tel_timer) tel_pend <= 1;", "		if (&tel_timer) tel_pend <= 2'd2;"),
("""			if (TELEMETRY && tel_pend) begin
				tel_pend  <= 0;
				tel_seq   <= tel_seq + 1'd1;
				ram_addr  <= BASE_TEL;
				ram_din   <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
				ram_be    <= 8'hFF;
				ram_burst <= 8'd1;
				ram_wr    <= 1;
				state     <= S_WR;
			end""",
 """			if (TELEMETRY && |tel_pend) begin
				tel_pend  <= tel_pend - 1'd1;
				ram_be    <= 8'hFF;
				ram_burst <= 8'd1;
				ram_wr    <= 1;
				state     <= S_WR;
				if (tel_pend == 2'd2) begin
					tel_seq  <= tel_seq + 1'd1;
					ram_addr <= BASE_TEL;
					ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
				end else begin
					ram_addr <= BASE_TEL + 25'd1;
					ram_din  <= tel_audio;
				end
			end"""),
])

# --- restore the /FDC DTACK wait
edit("rtl/GEN/ba.sv", [
("""			MBUS_FDC_READ:
				// NOTE (deferred, see HANDOFF): the Mega CD answers $A12000 with its own /DTACK and the old gen
				// waited for it; waiting here hangs the boot when nothing answers, so keep srg320's
				// auto-termination until the corruption work is picked up again.
				begin""",
 """			MBUS_FDC_READ:
				// The Mega CD gate array answers $A12000 ( /FDC ) with its own /DTACK, and srg320's older
				// Mega CD gen waited for it. This arbiter came from the 32X core, which has no expansion
				// device, so it auto-terminated - returning the register before the ASIC drove it. Games
				// boot either way because the BIOS is forgiving; mcd-verificator polls these registers raw
				// and hangs at "System init...". Waiting is what the hardware does.
				if (!DTACK_N) begin"""),
])
