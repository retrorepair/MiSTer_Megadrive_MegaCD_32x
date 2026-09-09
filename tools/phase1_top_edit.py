#!/usr/bin/env python3
"""Phase 1 merge: rewrite the MegaCD top (copied from srg320 MegaCD_MiSTer) for the S32X-revision gen.sv,
the 5-port SDRAM, PCM RAM in SDRAM, the 50 MHz Mega CD enable, and no Game Genie.
Every replacement asserts its anchor text so a drift in the source fails loudly.
Usage: phase1_top_edit.py <core/MegaCD.sv>"""
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8", errors="replace").read()

def rep(old, new):
    global s
    assert old in s, "anchor missing: " + old[:70]
    s = s.replace(old, new, 1)

def rex(pat, new):
    global s
    out, n = re.subn(pat, lambda m: new, s, count=1, flags=re.S | re.M)
    assert n == 1, "regex missing: " + pat[:70]
    s = out

# 1. bus strobe wires (new gen names; work RAM lives inside the new gen)
rep("wire        GEN_WRL_N, GEN_WRH_N, GEN_OE_N;\nwire        GEN_ROM_CE_N;\nwire        GEN_RAM_CE_N;\n",
    "wire        GEN_LWR_N, GEN_UWR_N, GEN_CAS0_N, GEN_CAS2_N;\nwire        GEN_ROM_CE_N;\n")

# 2. gen instantiation
GEN = '''gen gen
(
	.RESET_N(~reset),
	.MCLK(clk_sys),

	.VA(GEN_VA),
	.VDI(GEN_VDI),
	.VDO(GEN_VDO),
	.RNW(GEN_RNW),
	.LDS_N(GEN_LDS_N),
	.UDS_N(GEN_UDS_N),
	.AS_N(GEN_AS_N),
	.DTACK_N(GEN_DTACK_N),
	.ASEL_N(GEN_ASEL_N),
	.VCLK_CE(GEN_VCLK_CE),
	.CE0_N(GEN_CE0_N),
	.LWR_N(GEN_LWR_N),
	.UWR_N(GEN_UWR_N),
	.CAS0_N(GEN_CAS0_N),
	.RAS2_N(GEN_RAS2_N),
	.CAS2_N(GEN_CAS2_N),
	.ROM_N(EXT_ROM_N),
	.FDC_N(EXT_FDC_N),
	.CART_N(CART_CART_N),
	.DISK_N(0),
	.TIME_N(GEN_PAGE_CE_N),

	// CD audio enters the console mix on the EXT channel: "CD Audio: Filtered" mixes it before the console LPF
	.EXT_SL(mcd_l),
	.EXT_SR(mcd_r),
	.EN_32X_PWM(status[27]),

	.LPF_MODE(status[15:14]),
	.EN_GEN_FM(EN_GEN_FM),
	.EN_GEN_PSG(EN_GEN_PSG),
	.DAC_LDATA(GEN_AUDL),
	.DAC_RDATA(GEN_AUDR),
	.DAC_CE(GEN_CE),

	.LOADING(rom_download),
	.PAL(PAL),
	.EXPORT(|region),
	.EN_HIFI_PCM(status[23]), // Option "N"
	.LADDER(~status[8]),
	.OBJ_LIMIT_HIGH(status[31]),
	.FMBUSY_QUIRK(1'b0),

	.RED(r),
	.GREEN(g),
	.BLUE(b),
	.YS_N(),
	.EDCLK(),
	.VS(vs),
	.HS(hs),
	.HBL(hblank),
	.VBL(vblank),
	.CE_PIX(ce_pix),
	.BORDER(status[29]),
	.INTERLACE(interlace),
	.FIELD(VGA_F1),
	.RESOLUTION(resolution),

	.J3BUT(~status[5]),
	.JOY_1(status[4] ^ status[46] ? joystick_1 : joystick_0),
	.JOY_2(status[4] ^ status[46] ? joystick_0 : joystick_1),
	.JOY_3(joystick_2),
	.JOY_4(joystick_3),
	.JOY_5(joystick_4),
	.MULTITAP(status[22:21]),

	.MOUSE(ps2_mouse),
	.MOUSE_OPT(status[20:18]),

	.GUN_OPT(|gun_mode),
	.GUN_TYPE(gun_type),
	.GUN_SENSOR(lg_sensor),
	.GUN_A(lg_a),
	.GUN_B(lg_b),
	.GUN_C(lg_c),
	.GUN_START(lg_start),

	.SERJOYSTICK_IN(SERJOYSTICK_IN),
	.SERJOYSTICK_OUT(SERJOYSTICK_OUT),
	.SER_OPT(SER_OPT),

	.MEM_RDY(~GEN_MEM_BUSY),

	.GG_RESET(1'b0),
	.GG_EN(1'b0),
	.GG_CODE('0),
	.GG_AVAILABLE(),

	.PAUSE_EN(1'b0),
	.BGA_EN(EN_VDP_BGA),
	.BGB_EN(EN_VDP_BGB),
	.SPR_EN(EN_VDP_SPR),
	.BG_GRID_EN(2'b00),
	.SPR_GRID_EN(1'b0),

	.DBG_M68K_A(),
	.DBG_VA_A()
);
'''
rex(r"^gen gen\n\(\n.*?^\);\n", GEN)

# 3. no transparency detect in the SV VDP: "Adaptive" composite blend behaves as Off
rep("wire TRANSP_DETECT;\n",
    "wire TRANSP_DETECT = 0; // the SystemVerilog VDP has no transparency detect; \"Adaptive\" blend = Off\n")

# 4. VDI mux: work RAM is inside the new gen; /TIME data (mappers) comes through VDI now
rep("""assign GEN_VDI = !GEN_RAM_CE_N ? GEN_MEM_DO_R :
					  !CART_DTACK_N ? CART_DO :
					  MCD_DO;""",
    """assign GEN_VDI = !GEN_PAGE_CE_N ? GEN_PAGE_DI :   // /TIME ($A130xx) mapper/EEPROM registers (the old gen took these on TIME_DI)
					  !CART_DTACK_N ? CART_DO :
					  MCD_DO;""")
rex(r"reg \[15:0\] GEN_MEM_DO_R;\nalways @\(posedge clk_sys\) begin\n\treg old_bsy;\n\t\n\told_bsy <= GEN_MEM_BUSY;\n\tif\(old_bsy & ~GEN_MEM_BUSY\) GEN_MEM_DO_R <= GEN_MEM_DO;\nend\n", "")

# 5. MCD: 50 MHz enable, PCM RAM in SDRAM, no Game Genie
rep("wire        gg_available2;\n\nMCD MCD\n(",
    """wire [15:0] MCD_PCMRAM_A;
wire  [7:0] MCD_PCMRAM_DO;
wire [15:0] MCD_PCMRAM_DI;
wire        MCD_PCMRAM_RD;
wire        MCD_PCMRAM_WR;
wire        MCD_PCMRAM_BUSY;

// The Mega CD block steps on ENABLE. The original core tied it high, running the sub-CPU, PCM chip
// and CDC at 53.69/4 = 13.42 MHz instead of 12.5 MHz (7.4% fast) and compensated only the interrupt
// timer divider. A 50 MHz enable restores the real rate for all of them (the Mega CD has its own
// 50 MHz crystal, region independent, while the console clock follows the region).
wire mcd_en;
CEGen mcd_cegen
(
	.CLK(clk_sys),
	.RST_N(~reset),
	.IN_CLK(PAL ? 53203423 : 53693175),
	.OUT_CLK(50000000),
	.CE(mcd_en)
);

MCD MCD
(""")
rep("\t.ENABLE(1),\n\t.MCD_RST_N(MCD_RST_N),", "\t.ENABLE(1),\n\t.EN50(mcd_en),\n\t.MCD_RST_N(MCD_RST_N),")
rep("\t.CDDA_WR_READY(MCD_CDDA_WR_READY),\n",
    """\t.CDDA_WR_READY(MCD_CDDA_WR_READY),

	.PCMRAM_A(MCD_PCMRAM_A),
	.PCMRAM_DO(MCD_PCMRAM_DO),
	.PCMRAM_DI(MCD_PCMRAM_DI[7:0]),
	.PCMRAM_RD(MCD_PCMRAM_RD),
	.PCMRAM_WR(MCD_PCMRAM_WR),
	.PCMRAM_BUSY(MCD_PCMRAM_BUSY),
""")
rep("""\t.LED_GREEN(MCD_LED_GREEN),

	.GG_RESET(code_download && ioctl_wr && !ioctl_addr),
	.GG_EN(status[24]),
	.GG_CODE({gg_code[95] & gg_code[128], gg_code[127:0]}),
	.GG_AVAILABLE(gg_available2)
);""", "\t.LED_GREEN(MCD_LED_GREEN)\n);")

# 6. SDRAM: 5-port controller (from the NukedMD-MegaCD project), fixed priority = port order
SDR = '''sdram sdram
(
	.*,
	.init(~locked),
	.clk(clk_ram),

	// main 68000 bus: cart ROM, cart RAM, Mega CD BIOS ROM (the 68K work RAM is inside gen now)
	.addr0(!CART_RAM_CE_N ? {5'b01110,GEN_VA[19:1]}     : //CART RAM E00000-EFFFFF
			 !CART_ROM_CE_N ? {2'b00,ROM_VA[22:1]}        : //CART ROM 000000-7FFFFF
			                  {8'b01111000,GEN_VA[16:1]} ),	//BIOS ROM F00000-F1FFFF
	.din0(GEN_VDO),
	.dout0(GEN_MEM_DO),
	.rd0((~GEN_ROM_CE_N | ~CART_RAM_CE_N | ~CART_ROM_CE_N) & ~GEN_CAS0_N),
	.wrl0(~CART_RAM_CE_N & ~GEN_LWR_N),
	.wrh0(~CART_RAM_CE_N & ~GEN_UWR_N),
	.busy0(GEN_MEM_BUSY),

	//MCD PRG-RAM: banks 2,3
	.addr1({(MCD_BANK23 ? 6'b100000 : 6'b011111),MCD_PRG_ADDR}), // 1000000-107FFFF / 0F80000-0FFFFFF
	.din1(MCD_PRG_DO),
	.dout1(sdr_do),
	.rd1(use_sdr & ~MCD_PRG_OE_N),
	.wrl1(use_sdr & ~MCD_PRG_WRL_N),
	.wrh1(use_sdr & ~MCD_PRG_WRH_N),
	.busy1(sdr_busy),

	//MCD PCM wave RAM (sub CPU, gate array DMA, sample fetch) - see rtl/pcm_mem.sv
	.addr2({6'b100001, 2'b00, MCD_PCMRAM_A}), // 1080000-108FFFF
	.din2({8'h00, MCD_PCMRAM_DO}),
	.dout2(MCD_PCMRAM_DI),
	.rd2(MCD_PCMRAM_RD),
	.wrl2(MCD_PCMRAM_WR),
	.wrh2(1'b0),
	.busy2(MCD_PCMRAM_BUSY),

	//Load/Save
	.addr3( rom_download ? (rom_cart_mode ? {2'b00,ioctl_addr[22:1]} : {6'b011110,ioctl_addr[18:1]}) : //ROM  000000-7FFFFF/F00000-F7FFFF
								  {5'b01110,tmpram_lba[9:0],tmpram_addr}),    //CART RAM E00000-EFFFFF for sd_*
	.din3(rom_download ? {ioctl_data[7:0],ioctl_data[15:8]} : {tmpram_dout,tmpram_dout}),
	.dout3(tmpram_din),
	.rd3(~rom_download & tmpram_req & ~bk_loading),
	.wrl3(rom_download ? ioctl_wait : (tmpram_req & bk_loading)),
	.wrh3(rom_download ? ioctl_wait : (tmpram_req & bk_loading)),
	.busy3(tmpram_busy),

	// spare
	.addr4('0),
	.din4('0),
	.dout4(),
	.rd4(1'b0),
	.wrl4(1'b0),
	.wrh4(1'b0),
	.busy4()
);
'''
rex(r"^sdram sdram\n\(\n.*?^\);\n", SDR)

# 7. backup-RAM change detect uses the new strobe names
rep("(~GEN_WRL_N | ~GEN_WRH_N)", "(~GEN_LWR_N | ~GEN_UWR_N)")

# 8. region comes from the BIOS header only (a cart download must not change the console region)
rep("\tif(ioctl_wr & rom_download) begin\n\t\tif(ioctl_addr == 'h1F0) begin",
    "\tif(ioctl_wr & rom_download & ~ioctl_index[6]) begin // BIOS download only: a cartridge cannot change the console's region\n\t\tif(ioctl_addr == 'h1F0) begin")

# 9. Game Genie removed everywhere (2 engines = ~2,900 ALMs)
rex(r"// Code loading for WIDE IO \(16 bit\)\nreg \[128:0\] gg_code;\nwire        gg_available = gg_available1 \| gg_available2;\n.*?^end\n\n", "")
rep("wire gg_available1;\n\n", "")
rep("~gg_available,", "1'b1,")
rep('\t"C,Cheats;",\n\t"H5OO,Cheats Enabled,Yes,No;",\n\t"-;",\n', '')
rep('\t"P1OA,CRAM Dots,Off,On;",\n', '')
rep("wire code_download = ioctl_download & &ioctl_index;\n", "")

open(p, "w", encoding="utf-8").write(s)
print("ok")
