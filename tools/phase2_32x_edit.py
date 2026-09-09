#!/usr/bin/env python3
"""Phase 2: adapt the vendored 32X block (core/rtl/S32X/32X.sv, IF.sv) to this core.
 - frame buffers off-chip: the VDP's FBD_*/LP_*/LB_* ports are passed up to the top (rtl/s32x_ddr.sv)
 - SH-2 clock enable at the real 23.011 MHz (3 of 7 clk_sys cycles) instead of clk_sys/2 = 26.85 MHz;
   srg320 left the exact pattern commented out in favour of /2 - parameter SH2_EXACT (default 1) selects it
 - the 68K vector-ROM overlay ($000000-$0000FF while ADEN=1) is qualified with /CE0 as on hardware: with no
   cartridge /CE0 covers $400000-$7FFFFF, so the Mega CD BIOS vectors at $000000 stay visible (CD32X boot)
Usage: phase2_32x_edit.py <core/rtl/S32X>"""
import sys, os
d = sys.argv[1]

def edit(fn, pairs):
    p = os.path.join(d, fn)
    s = open(p, encoding="utf-8", errors="replace").read()
    s = "\n".join(l.rstrip() for l in s.replace("\r\n", "\n").split("\n"))
    for old, new in pairs:
        assert old in s, fn + ": anchor missing: " + old[:70]
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8").write(s)
    print(fn, "ok")

edit("32X.sv", [
("module S32X\n#(parameter bit USE_ROM_WAIT=0, bit USE_ASYNC_FB=1)\n(",
 "module S32X\n#(parameter bit USE_ROM_WAIT=0, bit SH2_EXACT=1)\n("),
("""	output     [15:0] FB0_A,
	input      [15:0] FB0_DI,
	output     [15:0] FB0_DO,
	output      [1:0] FB0_WE,
	output            FB0_RD,
	output     [15:0] FB1_A,
	input      [15:0] FB1_DI,
	output     [15:0] FB1_DO,
	output      [1:0] FB1_WE,
	output            FB1_RD,
""", """	// frame buffers in DDR3 (rtl/s32x_ddr.sv): draw port, line prefetch, line buffer
	output            FBD_FB,
	output     [15:0] FBD_A,
	output     [15:0] FBD_DO,
	output      [1:0] FBD_WE,
	output            FBD_RD,
	input      [15:0] FBD_DI,
	input             FBD_BUSY,
	input             FBD_RDY,
	output            LP_REQ,
	output            LP_FB,
	output      [7:0] LP_LINE,
	input      [15:0] LP_START,
	input      [15:0] LP_BASE,
	output      [8:0] LB_ADDR,
	input      [15:0] LB_Q,
"""),
("""	bit CE_R, CE_F;
	always @(posedge CLK) begin
		bit [2:0] CLK_CNT;
		CLK_CNT <= CLK_CNT == 3'd6 ? 3'd0 : CLK_CNT + 3'd1;

//		CE_F <= 0;
//		CE_R <= 0;
//		case (CLK_CNT)
//			3'd0: CE_F <= 1;
//			3'd1: CE_R <= 1;
//			3'd2: CE_F <= 1;
//			3'd3: CE_R <= 1;
//			3'd5: CE_F <= 1;
//			3'd6: CE_R <= 1;
//			default:;
//		endcase
		CE_F <= ~CE_F;
		CE_R <= CE_F;
	end
""", """	// SH-2 clock: 23.011 MHz = 3 x VCLK = 3/7 of the 53.69 MHz master clock on the real 32X.
	// SH2_EXACT=1 steps the SH-2s on 3 of every 7 clocks (F,R alternate: 0F 1R 2F 3R 5F 6R);
	// SH2_EXACT=0 keeps srg320's clk_sys/2 = 26.85 MHz (17 % fast).
	bit CE_R, CE_F;
	always @(posedge CLK) begin
		bit [2:0] CLK_CNT;
		CLK_CNT <= CLK_CNT == 3'd6 ? 3'd0 : CLK_CNT + 3'd1;

		if (SH2_EXACT) begin
			CE_F <= 0;
			CE_R <= 0;
			case (CLK_CNT)
				3'd0: CE_F <= 1;
				3'd1: CE_R <= 1;
				3'd2: CE_F <= 1;
				3'd3: CE_R <= 1;
				3'd5: CE_F <= 1;
				3'd6: CE_R <= 1;
				default:;
			endcase
		end else begin
			CE_F <= ~CE_F;
			CE_R <= CE_F;
		end
	end
"""),
("	S32X_VDP #(USE_ASYNC_FB) S32X_VDP\n", "	S32X_VDP S32X_VDP\n"),
("	input             ROM_WAIT,\n", "	input             ROM_WAIT,\n	input             CART_EXT,\n"),
("		.ROM_WAIT(ROM_WAIT)\n	);", "		.ROM_WAIT(ROM_WAIT),\n		.CART_EXT(CART_EXT)\n	);"),
("""		.FB0_A(FB0_A),
		.FB0_DI(FB0_DI),
		.FB0_DO(FB0_DO),
		.FB0_WE(FB0_WE),
		.FB0_RD(FB0_RD),

		.FB1_A(FB1_A),
		.FB1_DI(FB1_DI),
		.FB1_DO(FB1_DO),
		.FB1_WE(FB1_WE),
		.FB1_RD(FB1_RD),
""", """		.FBD_FB(FBD_FB),
		.FBD_A(FBD_A),
		.FBD_DO(FBD_DO),
		.FBD_WE(FBD_WE),
		.FBD_RD(FBD_RD),
		.FBD_DI(FBD_DI),
		.FBD_BUSY(FBD_BUSY),
		.FBD_RDY(FBD_RDY),
		.LP_REQ(LP_REQ),
		.LP_FB(LP_FB),
		.LP_LINE(LP_LINE),
		.LP_START(LP_START),
		.LP_BASE(LP_BASE),
		.LB_ADDR(LB_ADDR),
		.LB_Q(LB_Q),
"""),
])

edit("IF.sv", [
("	wire MD_BIOS_SEL = VA_SYNC[21:8] == 14'h0000 & ADCR.ADEN;								//000000-0000FF",
 "	// the 68K vector ROM sits on the cartridge chip select: with no cartridge /CE0 is $400000-$7FFFFF and the\n"
 "	// Mega CD BIOS keeps $000000 (a CD32X disc enables ADEN with the slot empty); srg320 decoded address bits only\n"
 "	wire MD_BIOS_SEL = VA_SYNC[21:8] == 14'h0000 & ADCR.ADEN & ~CE0_N_SYNC[0];					//000000-0000FF on /CE0"),
# Every MD access that passes through to the cartridge connector (/CE0, not the vector overlay) is run by the same
# state machine as the $880000 ROM window, so the MD gets /DTACK only when the cartridge side has answered and the
# SH-2s' ROM fetches are arbitrated against it. On hardware the 32X drives the slot's /DTACK for exactly this reason;
# srg320 let the console auto-terminate those cycles (MEM_RDY), which races the SDRAM in this core.
("	input             ROM_WAIT,\n",
 "	input             ROM_WAIT,\n	input             CART_EXT,		// the cartridge is fetching/storing for the current pass-through cycle (ROM_WAIT will rise)\n"),
("	bit [15:0] MD_ROM_DO;\n	bit        MD_ROM_DTACK_N;\n",
 "	bit [15:0] MD_ROM_DO;\n	bit        MD_ROM_DTACK_N;\n	bit        MD_ROM_PASS;		// this MD cycle is a /CE0 pass-through (any ADEN), not the $880000 window\n"),
("""			if (MD_32XROM_SEL && !AS_N_SYNC[0] && (LWR_F || UWR_F || CAS0_F)) begin
				MD_ROM_WAIT <= 1;
			end
""", """			if ((MD_32XROM_SEL || (!CE0_N_SYNC[0] && !MD_BIOS_SEL)) && !AS_N_SYNC[0] && (LWR_F || UWR_F || CAS0_F)) begin
				MD_ROM_WAIT <= 1;
				MD_ROM_PASS <= !MD_32XROM_SEL;
			end
"""),
("					end else if (MD_ROM_WAIT && ADCR.ADEN && !DCR.RV) begin\n						S32X_CE0 <= 1;\n						ROM_ST <= RS_MD_RW;\n",
 "					end else if (MD_ROM_WAIT && (MD_ROM_PASS || (ADCR.ADEN && !DCR.RV))) begin\n						S32X_CE0 <= 1;\n						ROM_ST <= RS_MD_RW;\n"),
("""				RS_MD_WAIT: begin
					if (ROM_WAIT_SYNC) begin
						ROM_ST <= RS_MD_READ;
					end
				end
""", """				RS_MD_WAIT: begin
					if (ROM_WAIT_SYNC) begin
						ROM_ST <= RS_MD_READ;
					end else if (MD_ROM_PASS && !CART_EXT) begin
						// nothing behind the connector fetches for this cycle (mapper register, EEPROM bit, empty slot): done
						ROM_ST <= RS_MD_READ;
					end
				end
"""),
])
