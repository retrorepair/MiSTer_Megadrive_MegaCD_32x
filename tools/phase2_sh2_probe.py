#!/usr/bin/env python3
"""Expose the two SH-2 program counters and the 32X bus state in the DDR3 telemetry, and default the
SH-2 clock to srg320's proven CLK/2 rate.

The counters in the first telemetry beat showed SH-2 work-RAM traffic frozen while the 68000 side kept
filling the frame buffer, so the SH-2s stop early. The PC says whether they sit in the boot ROM handshake,
spin in cartridge ROM, or have run off into nothing; the bus state says whether they are stalled on a fetch.

Telemetry map (read with tools/mister/hpsmem.py):
  0x30200000  magic 5332, seq, SH-2 RAM reads/writes, FB draw writes, line prefetches   (already present)
  0x30200008  { master SH-2 PC[31:0], slave SH-2 PC[31:0] }
  0x30200010  { magic 5333, 32X bus state: ADEN RES RV ROM_ST SH_ROM_WAIT MD_ROM_WAIT SHWAIT_N ... }

Usage: phase2_sh2_probe.py <core dir>"""
import sys, os
d = sys.argv[1]

def edit(rel, pairs):
    p = os.path.join(d, rel)
    s = open(p, encoding="utf-8", errors="replace").read()
    s = "\n".join(l.rstrip() for l in s.replace("\r\n", "\n").split("\n"))
    for old, new in pairs:
        assert old in s, rel + ": anchor missing: " + old[:60]
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(s)
    print(rel, "ok")

# 1. SH_core: always-on PC output (the DEBUG block already reads PIPE.WB.PC)
edit("rtl/SH/core/SH_core.sv", [
("\toutput            SLEEP\n", "\toutput            SLEEP,\n\toutput     [31:0] DBG_PC\t// retired PC, for the DDR3 telemetry\n"),
("\tassign SLEEP = SLP;\n", "\tassign SLEEP = SLP;\n\tassign DBG_PC = PIPE.WB.PC;\n"),
])

# 2. SH7604: pass it up
edit("rtl/SH/SH7604/SH7604.sv", [
("\tinput       [5:0] MD\n", "\tinput       [5:0] MD,\n\toutput     [31:0] DBG_PC\n"),
("\t\t.SLEEP(SLEEP)\n", "\t\t.SLEEP(SLEEP),\n\t\t.DBG_PC(DBG_PC)\n"),
])

# 3. 32X: expose both PCs and the ROM-path state; default the SH-2 clock to CLK/2
edit("rtl/S32X/32X.sv", [
("\toutput     [23:0] DBG_CA\n", "\toutput     [23:0] DBG_CA,\n\toutput     [31:0] DBG_MSH_PC,\n\toutput     [31:0] DBG_SSH_PC,\n\toutput     [15:0] DBG_STATE\n"),
("\t\t.MD(6'b001000)\n\t);", "\t\t.MD(6'b001000),\n\t\t.DBG_PC(DBG_MSH_PC)\n\t);"),
("\t\t.MD(6'b101000)\n\t);", "\t\t.MD(6'b101000),\n\t\t.DBG_PC(DBG_SSH_PC)\n\t);"),
("\tassign DBG_CA = {CA,1'b0};",
 "\tassign DBG_CA = {CA,1'b0};\n\tassign DBG_STATE = {SHRES_N, SHWAIT_N, SHCS1_N, SHCS3_N, SHBS_N, SHRD_N, SDR_CS, SDR_WAIT, IF_DBG_STATE};"),
("\t\t.ROM_WAIT(ROM_WAIT),\n\t\t.CART_EXT(CART_EXT)\n\t);",
 "\t\t.ROM_WAIT(ROM_WAIT),\n\t\t.CART_EXT(CART_EXT),\n\t\t.DBG_STATE(IF_DBG_STATE)\n\t);"),
("\tbit [ 15:0] IF_DO;", "\tbit  [7:0] IF_DBG_STATE;\n\tbit [ 15:0] IF_DO;"),
])

# 4. IF: report the ROM arbiter state and the 32X enables
edit("rtl/S32X/IF.sv", [
("\tinput             CART_EXT,", "\tinput             CART_EXT,\n\toutput      [7:0] DBG_STATE,"),
("\tassign SEL = SH_ROM_GRANT;",
 "\tassign SEL = SH_ROM_GRANT;\n\tassign DBG_STATE = {ADCR.ADEN, ADCR.RES, DCR.RV, SH_ROM_GRANT, ROM_ST[2:0], CART_EXT};"),
])

# 5. top: default the SH-2 clock to srg320's CLK/2 (status bit 2 now selects the exact 23.011 MHz instead)
edit("MegaCD.sv", [
('\t"H2O[2],SH2 Clock,23.0MHz,26.8MHz;",\n', '\t"H2O[2],SH2 Clock,26.8MHz,23.0MHz;",\n'),
("\t.SH2_DIV2(status[2]),", "\t.SH2_DIV2(~status[2]),   // default = srg320's CLK/2; bit 2 selects the exact 23.011 MHz"),
("\t.DBG_CA()\n);", "\t.DBG_CA(),\n\t.DBG_MSH_PC(S32X_MSH_PC),\n\t.DBG_SSH_PC(S32X_SSH_PC),\n\t.DBG_STATE(S32X_DBG_STATE)\n);"),
("wire [15:0] S32X_PWM_L, S32X_PWM_R;",
 "wire [15:0] S32X_PWM_L, S32X_PWM_R;\nwire [31:0] S32X_MSH_PC, S32X_SSH_PC;\nwire [15:0] S32X_DBG_STATE;"),
("\t.lb_addr(S32X_LB_ADDR),\n\t.lb_q(S32X_LB_Q)\n);",
 "\t.lb_addr(S32X_LB_ADDR),\n\t.lb_q(S32X_LB_Q),\n\n\t.tel_msh_pc(S32X_MSH_PC),\n\t.tel_ssh_pc(S32X_SSH_PC),\n\t.tel_state(S32X_DBG_STATE)\n);"),
])

# 6. s32x_ddr: two more telemetry beats
edit("rtl/s32x_ddr.sv", [
("\toutput     [15:0] lb_q          // registered: valid the clock after lb_addr\n);",
 "\toutput     [15:0] lb_q,         // registered: valid the clock after lb_addr\n\n\t// telemetry inputs (see tools/phase2_sh2_probe.py)\n\tinput      [31:0] tel_msh_pc,\n\tinput      [31:0] tel_ssh_pc,\n\tinput      [15:0] tel_state\n);"),
("reg  [16:0] tel_timer = 0;\nreg         tel_pend = 0;",
 "reg  [16:0] tel_timer = 0;\nreg   [1:0] tel_pend = 0;    // 3 = counters, 2 = PCs, 1 = 32X state"),
("\t\ttel_timer <= tel_timer + 1'd1;\n\t\tif (&tel_timer) tel_pend <= 1;",
 "\t\ttel_timer <= tel_timer + 1'd1;\n\t\tif (&tel_timer) tel_pend <= 2'd3;"),
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
				case (tel_pend)
					2'd3: begin
						tel_seq  <= tel_seq + 1'd1;
						ram_addr <= BASE_TEL;
						ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
					end
					2'd2: begin
						ram_addr <= BASE_TEL + 25'd1;
						ram_din  <= {tel_msh_pc, tel_ssh_pc};
					end
					default: begin
						ram_addr <= BASE_TEL + 25'd2;
						ram_din  <= {16'h5333, tel_state, 32'h00000000};
					end
				endcase
			end"""),
])
