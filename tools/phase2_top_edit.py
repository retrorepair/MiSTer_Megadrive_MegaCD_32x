#!/usr/bin/env python3
"""Phase 2 (applied after phase1_top_edit.py and phase1_top_edit2.py): put the 32X in the cartridge slot.
 - gen -> S32X block -> cart.sv (S32X's cart module, which works from the 32X's pass-through strobes) -> SDRAM port 0
 - 32X frame buffers and SH-2 work RAM in DDR3 through rtl/s32x_ddr.sv (the old, unused PRG-RAM-in-DDR3 path is removed)
 - SDRAM ports: 0 cartridge (MD or SH-2, via the 32X), 1 Mega CD BIOS, 2 PRG-RAM, 3 PCM RAM, 4 load/save
 - 32X video overlaid on the MD picture by YSO_N; PWM added to the EXT channel with the CD audio
 - S32X's cartridge quirk detection (EEPROM/SSF2/Realtec/SF mappers, FM-busy) replaces the top's own mapper/Pier logic
Usage: phase2_top_edit.py <core/MegaCD.sv>"""
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

# ---- OSD: 32X carts are cartridges too
rep('\t"FS6,BINGENMD,Insert Cartridge;",\n', '\t"FS6,BINGENMD32X,Insert Cartridge;",\n')

# ---- gen: 32X-side signals, PWM/CD on the EXT channel, cart-header quirk
rep("\t.YS_N(),\n\t.EDCLK(),\n", "\t.YS_N(YS_N),\n\t.EDCLK(EDCLK),\n")
rep("""	// CD audio enters the console mix on the EXT channel: "CD Audio: Filtered" mixes it before the console LPF
	.EXT_SL(mcd_l),
	.EXT_SR(mcd_r),
	.EN_32X_PWM(status[27]),
""", """	// the EXT channel mixes before the console LPF: 32X PWM always (cartridge-port audio in), CD audio when
	// "CD Audio: Filtered" is chosen (otherwise it is added after the LPF below, as upstream did)
	.EXT_SL(ext_l),
	.EXT_SR(ext_r),
	.EN_32X_PWM(1'b1),
""")
rep("\t.FMBUSY_QUIRK(1'b0),\n", "\t.FMBUSY_QUIRK(fmbusy_quirk),\n")

# ---- bus data/DTACK: the 32X (and the cartridge behind it) or the Mega CD
rep("""assign GEN_VDI = !GEN_PAGE_CE_N ? GEN_PAGE_DI :   // /TIME ($A130xx) mapper/EEPROM registers (the old gen took these on TIME_DI)
					  !CART_DTACK_N ? CART_DO :
					  MCD_DO;
assign GEN_DTACK_N = MCD_DTACK_N & CART_DTACK_N;
""", """// The 32X sits in the cartridge slot: everything on /CE0, /TIME and its own windows comes back through it
// (cart.sv answers behind it on the pass-through bus); the Mega CD is on the expansion port.
assign GEN_VDI = (~S32X_DTACK_N | ~GEN_PAGE_CE_N) ? S32X_VDO : MCD_DO;
assign GEN_DTACK_N = MCD_DTACK_N & S32X_DTACK_N & CART_DTACK_N;
""")

# ---- audio: CD (+ PWM) on the EXT channel
rep("""reg [15:0] aud_l, aud_r;
reg [15:0] cmp_l, cmp_r;
reg [15:0] mcd_l, mcd_r;
always @(posedge clk_sys) begin
	mcd_l <= ({16{EN_MCD_PCM}} & {MCD_PCM_SL[15],MCD_PCM_SL[15:1]}) + ({16{EN_MCD_CDDA}} & {MCD_CDDA_SL[15],MCD_CDDA_SL[15:1]});
	mcd_r <= ({16{EN_MCD_PCM}} & {MCD_PCM_SR[15],MCD_PCM_SR[15:1]}) + ({16{EN_MCD_CDDA}} & {MCD_CDDA_SR[15],MCD_CDDA_SR[15:1]});
""", """function [15:0] sat16(input [16:0] v);   // saturating 17 -> 16 bit
	sat16 = (v[16] != v[15]) ? {v[16], {15{~v[16]}}} : v[15:0];
endfunction

reg [15:0] aud_l, aud_r;
reg [15:0] cmp_l, cmp_r;
reg [15:0] mcd_l, mcd_r;
reg [15:0] ext_l, ext_r;
wire [15:0] pwm_l = {16{EN_32X_PWM}} & S32X_PWM_L;
wire [15:0] pwm_r = {16{EN_32X_PWM}} & S32X_PWM_R;
always @(posedge clk_sys) begin
	mcd_l <= ({16{EN_MCD_PCM}} & {MCD_PCM_SL[15],MCD_PCM_SL[15:1]}) + ({16{EN_MCD_CDDA}} & {MCD_CDDA_SL[15],MCD_CDDA_SL[15:1]});
	mcd_r <= ({16{EN_MCD_PCM}} & {MCD_PCM_SR[15],MCD_PCM_SR[15:1]}) + ({16{EN_MCD_CDDA}} & {MCD_CDDA_SR[15],MCD_CDDA_SR[15:1]});
	ext_l <= sat16({pwm_l[15],pwm_l} + (status[27] ? {mcd_l[15],mcd_l} : 17'd0));
	ext_r <= sat16({pwm_r[15],pwm_r} + (status[27] ? {mcd_r[15],mcd_r} : 17'd0));
""")

# ---- the cartridge slot: 32X block + cart.sv + DDR3 memories replace the VHDL CART
rex(r"//ROM/RAM Cart\nwire \[15:0\] CART_DO;\n.*?^\);\n\nalways @\(posedge clk_sys\) begin\n\treg old_busy;\n", r"""//////////////////////////////////////////////////////////////////
// Cartridge slot: the 32X, with the game cartridge (cart.sv) behind it on the 32X's pass-through bus

wire        CART_CART_N = ~rom_cart_mode;   // a cartridge in the slot grounds /CART (the 32X passes the pin through)
wire        CART_EN = status[3];            // "Backup RAM: Internal+Cart": also save/load the cartridge SRAM region
wire        EN_32X_PWM = ~status[63] | ~dbg_menu;
wire        YS_N, EDCLK;

wire [15:0] S32X_VDO;
wire        S32X_DTACK_N;
wire [23:1] S32X_CA;
wire [15:0] S32X_CDI, S32X_CDO;
wire        S32X_CASEL_N, S32X_CLWR_N, S32X_CUWR_N, S32X_CCE0_N, S32X_CCAS0_N, S32X_CCAS2_N;
wire [17:1] S32X_SDR_A;
wire [15:0] S32X_SDR_DI, S32X_SDR_DO;
wire        S32X_SDR_CS, S32X_SDR_RD, S32X_SDR_WAIT;
wire  [1:0] S32X_SDR_WE;
wire        S32X_FBD_FB, S32X_FBD_RD, S32X_FBD_BUSY, S32X_FBD_RDY;
wire [15:0] S32X_FBD_A, S32X_FBD_DO, S32X_FBD_DI;
wire  [1:0] S32X_FBD_WE;
wire        S32X_LP_REQ, S32X_LP_FB;
wire  [7:0] S32X_LP_LINE;
wire [15:0] S32X_LP_START, S32X_LP_BASE;
wire  [8:0] S32X_LB_ADDR;
wire [15:0] S32X_LB_Q;
wire  [4:0] S32X_R, S32X_G, S32X_B;
wire        S32X_YSO_N;
wire [15:0] S32X_PWM_L, S32X_PWM_R;

S32X #(.USE_ROM_WAIT(1), .SH2_EXACT(1)) S32X
(
	.CLK(clk_sys),
	.RST_N(~(reset | rom_download)),

	.VCLK(GEN_VCLK_CE),
	.VA(GEN_VA),
	.VDI(GEN_VDO),
	.VDO(S32X_VDO),
	.AS_N(GEN_AS_N),
	.DTACK_N(S32X_DTACK_N),
	.LWR_N(GEN_LWR_N),
	.UWR_N(GEN_UWR_N),
	.CE0_N(GEN_CE0_N),
	.CAS0_N(GEN_CAS0_N),
	.CAS2_N(GEN_CAS2_N),
	.ASEL_N(GEN_ASEL_N),
	.VRES_N(1'b1),
	.MRES_N(1'b1),
	.CART_N(CART_CART_N),

	.EDCLK(EDCLK),
	.VSYNC_N(vs),
	.HSYNC_N(hs),
	.YS_N(YS_N),
	.PAL(PAL),

	.CA(S32X_CA),
	.CDI(S32X_CDI),
	.CDO(S32X_CDO),
	.CASEL_N(S32X_CASEL_N),
	.CLWR_N(S32X_CLWR_N),
	.CUWR_N(S32X_CUWR_N),
	.CCE0_N(S32X_CCE0_N),
	.CCAS0_N(S32X_CCAS0_N),
	.CCAS2_N(S32X_CCAS2_N),
	.ROM_WAIT(CART_MEM_BUSY),
	.CART_EXT(CART_EXT),

	.SDR_A(S32X_SDR_A),
	.SDR_DI(S32X_SDR_DI),
	.SDR_DO(S32X_SDR_DO),
	.SDR_CS(S32X_SDR_CS),
	.SDR_WE(S32X_SDR_WE),
	.SDR_RD(S32X_SDR_RD),
	.SDR_WAIT(S32X_SDR_WAIT),

	.FBD_FB(S32X_FBD_FB),
	.FBD_A(S32X_FBD_A),
	.FBD_DO(S32X_FBD_DO),
	.FBD_WE(S32X_FBD_WE),
	.FBD_RD(S32X_FBD_RD),
	.FBD_DI(S32X_FBD_DI),
	.FBD_BUSY(S32X_FBD_BUSY),
	.FBD_RDY(S32X_FBD_RDY),
	.LP_REQ(S32X_LP_REQ),
	.LP_FB(S32X_LP_FB),
	.LP_LINE(S32X_LP_LINE),
	.LP_START(S32X_LP_START),
	.LP_BASE(S32X_LP_BASE),
	.LB_ADDR(S32X_LB_ADDR),
	.LB_Q(S32X_LB_Q),

	.R(S32X_R),
	.G(S32X_G),
	.B(S32X_B),
	.HS_N(),
	.VS_N(),
	.YSO_N(S32X_YSO_N),

	.PWM_L(S32X_PWM_L),
	.PWM_R(S32X_PWM_R),

	.DBG_CA()
);

// the game cartridge behind the 32X (mappers, SRAM, EEPROM); ROM and SRAM live in SDRAM port 0
wire [15:0] CART_DO;
wire        CART_DTACK_N;
wire [23:1] CART_ROM_A;
wire [15:0] CART_ROM_DO;
wire        CART_ROM_RD, CART_ROM_WRL, CART_ROM_WRH;
wire [14:0] CART_SRAM_A;
wire  [7:0] CART_SRAM_DO;
wire        CART_SRAM_RD, CART_SRAM_WR;
wire [15:0] CART_MEM_DO;
wire        CART_MEM_BUSY;
wire        CART_SRAM_ACC = CART_SRAM_RD | CART_SRAM_WR;
wire        CART_EXT = CART_ROM_RD | CART_ROM_WRL | CART_ROM_WRH | CART_SRAM_ACC;

CART cart
(
	.CLK(clk_sys),
	.RST_N(~(reset | rom_download)),

	.VCLK(GEN_VCLK_CE),
	.VA(S32X_CA),
	.VDI(S32X_CDO),
	.VDO(CART_DO),
	.AS_N(GEN_AS_N),
	.DTACK_N(CART_DTACK_N),
	.LWR_N(S32X_CLWR_N),
	.UWR_N(S32X_CUWR_N),
	.CE0_N(S32X_CCE0_N),
	.CAS0_N(S32X_CCAS0_N),
	.CAS2_N(S32X_CCAS2_N),
	.ASEL_N(S32X_CASEL_N),
	.TIME_N(GEN_PAGE_CE_N),

	.ROM_A(CART_ROM_A),
	.ROM_DI(CART_MEM_DO),
	.ROM_DO(CART_ROM_DO),
	.ROM_RD(CART_ROM_RD),
	.ROM_WRL(CART_ROM_WRL),
	.ROM_WRH(CART_ROM_WRH),

	.SRAM_A(CART_SRAM_A),
	.SRAM_DI(CART_MEM_DO[7:0]),
	.SRAM_DO(CART_SRAM_DO),
	.SRAM_RD(CART_SRAM_RD),
	.SRAM_WR(CART_SRAM_WR),

	.rom_sz(rom_sz[23:0]),
	.eeprom_map(eeprom_map),
	.bank_eeprom_quirk(bank_eeprom_quirk),
	.noram_quirk(noram_quirk),
	.schan_quirk(schan_quirk),
	.realtec_map(realtec_map),
	.sf_map(sf_map)
);
assign S32X_CDI = CART_DO;

// 32X frame buffers and SH-2 work RAM in the HPS DDR3
s32x_ddr s32x_ddr
(
	.clk(clk_sys),
	.reset(reset | rom_download),

	.DDRAM_CLK(DDRAM_CLK),
	.DDRAM_BUSY(DDRAM_BUSY),
	.DDRAM_BURSTCNT(DDRAM_BURSTCNT),
	.DDRAM_ADDR(DDRAM_ADDR),
	.DDRAM_DOUT(DDRAM_DOUT),
	.DDRAM_DOUT_READY(DDRAM_DOUT_READY),
	.DDRAM_RD(DDRAM_RD),
	.DDRAM_DIN(DDRAM_DIN),
	.DDRAM_BE(DDRAM_BE),
	.DDRAM_WE(DDRAM_WE),

	.sdr_addr(S32X_SDR_A),
	.sdr_din(S32X_SDR_DO),
	.sdr_dout(S32X_SDR_DI),
	.sdr_rd(S32X_SDR_CS & S32X_SDR_RD),
	.sdr_wr({2{S32X_SDR_CS}} & S32X_SDR_WE),
	.sdr_busy(S32X_SDR_WAIT),

	.fbd_fb(S32X_FBD_FB),
	.fbd_addr(S32X_FBD_A),
	.fbd_din(S32X_FBD_DO),
	.fbd_dout(S32X_FBD_DI),
	.fbd_rd(S32X_FBD_RD),
	.fbd_wr(S32X_FBD_WE),
	.fbd_busy(S32X_FBD_BUSY),
	.fbd_rdy(S32X_FBD_RDY),

	.lp_req(S32X_LP_REQ),
	.lp_fb(S32X_LP_FB),
	.lp_line(S32X_LP_LINE),
	.lp_start(S32X_LP_START),
	.lp_base(S32X_LP_BASE),
	.lp_done(),

	.lb_addr(S32X_LB_ADDR),
	.lb_q(S32X_LB_Q)
);

always @(posedge clk_sys) begin
	reg old_busy;
""")

# ---- old DDR3 PRG-RAM option removed; SDRAM ports re-assigned
rex(r"wire use_sdr = 1;\n\nassign MCD_PRG_BUSY = use_sdr \? sdr_busy : ddr_busy;\nassign MCD_PRG_DI   = use_sdr \? sdr_do   : ddr_do;\n\nwire ddr_busy;\nwire \[15:0\] ddr_do;\nassign DDRAM_CLK = clk_ram & ~use_sdr;\nddram ddram\n\(.*?^\);\n",
    "assign MCD_PRG_BUSY = sdr_busy;\nassign MCD_PRG_DI   = sdr_do;\n")
rex(r"^sdram sdram\n\(\n.*?^\);\n", '''sdram sdram
(
	.*,
	.init(~locked),
	.clk(clk_ram),

	// cartridge (MD or SH-2 through the 32X): ROM 0000000-0DFFFFF, SRAM 0E00000-0EFFFFF (one byte per word, low lane)
	.addr0(CART_SRAM_ACC ? {9'b011100000, CART_SRAM_A[14:0]} : {1'b0, CART_ROM_A[23:1]}),
	.din0(CART_SRAM_ACC ? {8'h00, CART_SRAM_DO} : CART_ROM_DO),
	.dout0(CART_MEM_DO),
	.rd0(CART_ROM_RD | CART_SRAM_RD),
	.wrl0(CART_ROM_WRL | CART_SRAM_WR),
	.wrh0(CART_ROM_WRH),
	.busy0(CART_MEM_BUSY),

	// Mega CD BIOS ROM (main CPU / VDP DMA) F00000-F1FFFF
	.addr1({8'b01111000, GEN_VA[16:1]}),
	.din1(16'h0000),
	.dout1(GEN_MEM_DO),
	.rd1(~GEN_ROM_CE_N & ~GEN_CAS0_N),
	.wrl1(1'b0),
	.wrh1(1'b0),
	.busy1(GEN_MEM_BUSY),

	//MCD PRG-RAM: banks 2,3
	.addr2({(MCD_BANK23 ? 6'b100000 : 6'b011111),MCD_PRG_ADDR}), // 1000000-107FFFF / 0F80000-0FFFFFF
	.din2(MCD_PRG_DO),
	.dout2(sdr_do),
	.rd2(~MCD_PRG_OE_N),
	.wrl2(~MCD_PRG_WRL_N),
	.wrh2(~MCD_PRG_WRH_N),
	.busy2(sdr_busy),

	//MCD PCM wave RAM (sub CPU, gate array DMA, sample fetch) - see rtl/pcm_mem.sv
	.addr3({6'b100001, 2'b00, MCD_PCMRAM_A}), // 1080000-108FFFF
	.din3({8'h00, MCD_PCMRAM_DO}),
	.dout3(MCD_PCMRAM_DI),
	.rd3(MCD_PCMRAM_RD),
	.wrl3(MCD_PCMRAM_WR),
	.wrh3(1'b0),
	.busy3(MCD_PCMRAM_BUSY),

	//Load/Save
	.addr4( rom_download ? (cart_download ? {1'b0,ioctl_addr[23:1]} : {6'b011110,ioctl_addr[18:1]}) : //ROM  000000-DFFFFF / BIOS F00000-F7FFFF
								  {5'b01110,tmpram_lba[9:0],tmpram_addr}),    //CART RAM E00000-EFFFFF for sd_*
	.din4(rom_download ? {ioctl_data[7:0],ioctl_data[15:8]} : {tmpram_dout,tmpram_dout}),
	.dout4(tmpram_din),
	.rd4(~rom_download & tmpram_req & ~bk_loading),
	.wrl4(rom_download ? ioctl_wait : (tmpram_req & bk_loading)),
	.wrh4(rom_download ? ioctl_wait : (tmpram_req & bk_loading)),
	.busy4(tmpram_busy)
);
''')

# ---- backup RAM block: no Pier EEPROM mux
rep("""	.address_a(PIER_QUIRK ? m95_addr : MCD_BRAM_ADDR),
	.data_a(PIER_QUIRK ? m95_di : MCD_BRAM_DO),
	.wren_a(PIER_QUIRK ? m95_we : MCD_BRAM_WE),""", """	.address_a(MCD_BRAM_ADDR),
	.data_a(MCD_BRAM_DO),
	.wren_a(MCD_BRAM_WE),""")
rep("wire bk_change  = MCD_BRAM_WE | m95_we | (CART_EN & ~CART_RAM_CE_N & (~GEN_LWR_N | ~GEN_UWR_N));",
    "wire bk_change  = MCD_BRAM_WE | (CART_EN & CART_SRAM_WR);")

# ---- video: the 32X picture is composited over the MD picture per pixel (YSO_N low = 32X pixel)
rep("""	.red(color_lut[r]),
	.green(color_lut[g]),
	.blue(color_lut[b]),
""", """	.red(vid_r),
	.green(vid_g),
	.blue(vid_b),
""")
rep("wire hs_c,vs_c,hblank_c,vblank_c;\n",
    """wire hs_c,vs_c,hblank_c,vblank_c;

// 32X overlay: the 32X VDP's pixel replaces the MD's where it is active (YSO_N low), as on the real stack
wire        EN_32X_VID = ~status[9] | ~dbg_menu;
wire        s32x_pix = ~S32X_YSO_N & EN_32X_VID;
wire  [7:0] vid_r = s32x_pix ? {S32X_R, S32X_R[4:2]} : color_lut[r];
wire  [7:0] vid_g = s32x_pix ? {S32X_G, S32X_G[4:2]} : color_lut[g];
wire  [7:0] vid_b = s32x_pix ? {S32X_B, S32X_B[4:2]} : color_lut[b];
""")

# ---- mapper / Pier Solar logic in the top is replaced by cart.sv + S32X's quirk detection
rex(r"reg         ep_si, m95_so, ep_sck, ep_hold, ep_cs;\n.*?\nreg \[23:13\] rom_mask;\n", "")
rep("""reg         rom_cart_mode = 0;
reg         cart_auto = 0;      // this cartridge came from cart.rom beside the disc, not from the OSD
always @(posedge clk_sys) begin
	reg old_cart_dl, old_bios_dl;
	old_cart_dl <= cart_download;
	old_bios_dl <= bios_download;
	if(~old_cart_dl & cart_download) begin
		rom_cart_mode <= 1;
		cart_auto <= ioctl_index[7:6] == 2'b01;   // 40/41 = cart.rom next to the CD
	end
	if(~old_bios_dl & bios_download & cart_auto) rom_cart_mode <= 0;
	if(cart_remove) begin
		rom_cart_mode <= 0;
		cart_auto <= 0;
	end
	if (cart_download & ioctl_wr) begin
		rom_mask <= rom_mask | ioctl_addr[23:13];
		if(!ioctl_addr) rom_mask <= 0;
	end
end""", """reg         rom_cart_mode = 0;
reg         cart_auto = 0;      // this cartridge came from cart.rom beside the disc, not from the OSD
reg  [24:0] rom_sz = 0;
always @(posedge clk_sys) begin
	reg old_cart_dl, old_bios_dl;
	old_cart_dl <= cart_download;
	old_bios_dl <= bios_download;
	if(~old_cart_dl & cart_download) begin
		rom_cart_mode <= 1;
		cart_auto <= ioctl_index[7:6] == 2'b01;   // 40/41 = cart.rom next to the CD
	end
	if(old_cart_dl & ~cart_download) rom_sz <= ioctl_addr[24:0];
	if(~old_bios_dl & bios_download & cart_auto) rom_cart_mode <= 0;
	if(cart_remove) begin
		rom_cart_mode <= 0;
		cart_auto <= 0;
	end
end

// cartridge header quirks (from S32X_MiSTer): mappers, EEPROM types, FM busy flag
reg [2:0] eeprom_map = 0;
reg bank_eeprom_quirk = 0;
reg realtec_map = 0;
reg noram_quirk = 0;
reg fmbusy_quirk = 0;
reg schan_quirk = 0;
reg [2:0] sf_map = '0;
always @(posedge clk_sys) begin
	reg [87:0] cart_id;
	reg [15:0] crc = '0;
	reg [31:0] realtec_id = '0;
	reg old_download;
	old_download <= cart_download;

	if(~old_download && cart_download) {eeprom_map,bank_eeprom_quirk,realtec_map,noram_quirk,fmbusy_quirk,schan_quirk,sf_map} <= 0;

	if(ioctl_wr & cart_download) begin
		if(ioctl_addr == 'h180) cart_id[87:72] <= {ioctl_data[7:0],ioctl_data[15:8]};
		if(ioctl_addr == 'h182) cart_id[71:56] <= {ioctl_data[7:0],ioctl_data[15:8]};
		if(ioctl_addr == 'h184) cart_id[55:40] <= {ioctl_data[7:0],ioctl_data[15:8]};
		if(ioctl_addr == 'h186) cart_id[39:24] <= {ioctl_data[7:0],ioctl_data[15:8]};
		if(ioctl_addr == 'h188) cart_id[23:08] <= {ioctl_data[7:0],ioctl_data[15:8]};
		if(ioctl_addr == 'h18A) cart_id[07:00] <= ioctl_data[7:0];
		if(ioctl_addr == 'h18E) crc <= {ioctl_data[7:0],ioctl_data[15:8]};
		if(ioctl_addr == 'h190) begin
			if     (cart_id[63:0] == "T-081276") bank_eeprom_quirk <= 1; // NFL Quarterback Club
			else if(cart_id[63:0] == "T-81406 ") bank_eeprom_quirk <= 1; // NBA Jam TE
			else if(cart_id[63:0] == "T-081586") bank_eeprom_quirk <= 1; // NFL Quarterback Club '96
			else if(cart_id[63:0] == "T-81576 ") bank_eeprom_quirk <= 1; // College Slam
			else if(cart_id[63:0] == "T-81476 ") bank_eeprom_quirk <= 1; // Frank Thomas Big Hurt Baseball
			else if(cart_id[63:0] == "T-50446 ") eeprom_map        <= 3'b001; // John Madden Football 93
			else if(cart_id[63:0] == "T-50516 ") eeprom_map        <= 3'b001; // John Madden Football 93 Championship Edition
			else if(cart_id[63:0] == "T-50396 ") eeprom_map        <= 3'b001; // NHLPA Hockey 93
			else if(cart_id[63:0] == "T-50176 ") eeprom_map        <= 3'b001; // Rings of Power
			else if(cart_id[63:0] == "T-50606 ") eeprom_map        <= 3'b001; // Bill Walsh College Football
			else if(cart_id[63:0] == "MK-1215 ") eeprom_map        <= 3'b010; // Evander Real Deal Holyfield's Boxing
			else if(cart_id[63:0] == "G-4060  ") eeprom_map        <= 3'b010; // Wonder Boy
			else if(cart_id[63:0] == "00001211") eeprom_map        <= 3'b010; // Sports Talk Baseball
			else if(cart_id[63:0] == "MK-1228 ") eeprom_map        <= 3'b010; // Greatest Heavyweights
			else if(cart_id[63:0] == "G-5538  ") eeprom_map        <= 3'b010; // Greatest Heavyweights JP
			else if(cart_id[63:0] == "00004076") eeprom_map        <= 3'b010; // Honoo no Toukyuuji Dodge Danpei
			else if(cart_id[63:0] == "T-12046 ") eeprom_map        <= 3'b010; // Mega Man - The Wily Wars
			else if(cart_id[63:0] == "T-12053 ") eeprom_map        <= 3'b010; // Rockman Mega World
			else if(cart_id[63:0] == "G-4524  ") eeprom_map        <= 3'b010; // Ninja Burai Densetsu
			else if(cart_id[63:0] == "00054503") eeprom_map        <= 3'b010; // Game Toshokan
			else if(cart_id[63:0] == "T-81033 ") eeprom_map        <= 3'b011; // NBA Jam (J)
			else if(cart_id[63:0] == "T-081326") eeprom_map        <= 3'b011; // NBA Jam (U)(E)
			else if(cart_id[63:0] == "T-113016") noram_quirk       <= 1; // Puggsy fake ram check
			else if(cart_id[63:0] == "T-35036 ") fmbusy_quirk      <= 1; // Hellfire US
			else if(cart_id[63:0] == "T-25073 ") fmbusy_quirk      <= 1; // Hellfire JP
			else if(cart_id[63:0] == "MK-1137-") fmbusy_quirk      <= 1; // Hellfire EU
			else if(cart_id[63:0] == "T-68???-") schan_quirk       <= 1; // Game no Kanzume Otokuyou
			else if(cart_id[87:40] == "SF-001")  sf_map            <= {crc == 16'h3E08,2'b01}; // Beggar Prince (Unl), rev 1
			else if(cart_id[87:40] == "SF-002")  sf_map            <= {1'b1,2'b10}; // Legend of Wukong (Unl)
			else if(cart_id[87:40] == "SF-004")  sf_map            <= {1'b1,2'b11}; // Star Odyssey (Unl)
		end

		if(ioctl_addr == 'h7E100) realtec_id[31:16] <= {ioctl_data[7:0],ioctl_data[15:8]};
		if(ioctl_addr == 'h7E102) realtec_id[15: 0] <= {ioctl_data[7:0],ioctl_data[15:8]};
		if(ioctl_addr == 'h7E104) begin
			if (realtec_id == "SEGA") realtec_map <= 1; // Earth Defend, Funny World & Balloon Boy, Whac-a-Critter
		end
	end
end""")

open(p, "w", encoding="utf-8").write(s)
print("ok")
