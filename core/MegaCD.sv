//============================================================================
//  FPGAGen port to MiSTer
//  Copyright (c) 2017-2019 Sorgelig
//
//  YM2612 implementation by Jose Tejada Gomez. Twitter: @topapate
//  Original Genesis code: Copyright (c) 2010-2013 Gregory Estrade (greg@torlus.com) 
//
//  This program is free software; you can redistribute it and/or modify it
//  under the terms of the GNU General Public License as published by the Free
//  Software Foundation; either version 2 of the License, or (at your option)
//  any later version.
//
//  This program is distributed in the hope that it will be useful, but WITHOUT
//  ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
//  FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for
//  more details.
//
//  You should have received a copy of the GNU General Public License along
//  with this program; if not, write to the Free Software Foundation, Inc.,
//  51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.
//============================================================================

module emu
(
	`include "sys/emu_ports.vh"
);

assign ADC_BUS  = 'Z;
assign {UART_RTS, UART_TXD, UART_DTR} = 0;
assign BUTTONS   = {bk_reload, 1'b0};
assign {SD_SCK, SD_MOSI, SD_CS} = 'Z;

assign LED_DISK  = {1'b1,MCD_LED_RED};
assign LED_POWER = {1'b1,MCD_LED_GREEN};
assign LED_USER  = rom_download | sav_pending;

assign VGA_SCALER= 0;
assign VGA_DISABLE = 0;
assign HDMI_FREEZE = 0;
assign HDMI_BLACKOUT = 0;
assign HDMI_BOB_DEINT = 0;

assign AUDIO_S   = 1;
assign AUDIO_MIX = 0;
wire [1:0] ar = status[50:49];
wire [7:0] arx,ary;

always_comb begin
	case(res) // {V30, H40}
		2'b00: begin // 256 x 224
			arx = 8'd64;
			ary = 8'd49;
		end

		2'b01: begin // 320 x 224
			arx = status[30] ? 8'd10: 8'd64;
			ary = status[30] ? 8'd7 : 8'd49;
		end

		2'b10: begin // 256 x 240
			arx = 8'd128;
			ary = 8'd105;
		end

		2'b11: begin // 320 x 240
			arx = status[30] ? 8'd4 : 8'd128;
			ary = status[30] ? 8'd3 : 8'd105;
		end
	endcase
end

wire       vcrop_en = status[32];
wire [3:0] vcopt    = status[54:51];
reg        en216p;
reg  [4:0] voff;
always @(posedge CLK_VIDEO) begin
	en216p <= ((HDMI_WIDTH == 1920) && (HDMI_HEIGHT == 1080) && !forced_scandoubler && !scale);
	voff <= (vcopt < 6) ? {vcopt,1'b0} : ({vcopt,1'b0} - 5'd24);
end

wire vga_de;
video_freak video_freak
(
	.*,
	.VGA_DE_IN(vga_de),
	.ARX((!ar) ? arx : (ar - 1'd1)),
	.ARY((!ar) ? ary : 12'd0),
	.CROP_SIZE((en216p & vcrop_en) ? 10'd216 : 10'd0),
	.CROP_OFF(voff),
	.SCALE(status[56:55])
);

///////////////////////////////////////////////////
wire clk_sys, clk_ram, locked;

pll pll
(
	.refclk(CLK_50M),
	.rst(0),
	.outclk_0(clk_ram),
	.outclk_1(clk_sys),
	.reconfig_to_pll(reconfig_to_pll),
	.reconfig_from_pll(reconfig_from_pll),
	.locked(locked)
);

wire [63:0] reconfig_to_pll;
wire [63:0] reconfig_from_pll;
wire        cfg_waitrequest;
reg         cfg_write;
reg   [5:0] cfg_address;
reg  [31:0] cfg_data;

pll_cfg pll_cfg
(
	.mgmt_clk(CLK_50M),
	.mgmt_reset(0),
	.mgmt_waitrequest(cfg_waitrequest),
	.mgmt_read(0),
	.mgmt_readdata(),
	.mgmt_write(cfg_write),
	.mgmt_address(cfg_address),
	.mgmt_writedata(cfg_data),
	.reconfig_to_pll(reconfig_to_pll),
	.reconfig_from_pll(reconfig_from_pll)
);

always @(posedge CLK_50M) begin
	reg pald = 0, pald2 = 0;
	reg [2:0] state = 0;
	reg pal_r;

	pald <= PAL;
	pald2 <= pald;

	cfg_write <= 0;
	if(pald2 == pald && pald2 != pal_r) begin
		state <= 1;
		pal_r <= pald2;
	end

	if(!cfg_waitrequest) begin
		if(state) state<=state+1'd1;
		case(state)
			1: begin
					cfg_address <= 0;
					cfg_data <= 0;
					cfg_write <= 1;
				end
			5: begin
					cfg_address <= 7;
					cfg_data <= pal_r ? 2201376125 : 2537930535;
					cfg_write <= 1;
				end
			7: begin
					cfg_address <= 2;
					cfg_data <= 0;
					cfg_write <= 1;
				end
		endcase
	end
end

// Status Bit Map:
//             Upper                             Lower              
// 0         1         2         3          4         5         6   
// 01234567890123456789012345678901 23456789012345678901234567890123
// 0123456789ABCDEFGHIJKLMNOPQRSTUV 0123456789ABCDEFGHIJKLMNOPQRSTUV
// XXXXXXXXX XXXXXXXXXXXXXXXXXX XXX XXXXXXXXXXXXXXXXXXXXXXXXXXX

`include "build_id.v"
localparam CONF_STR = {
	"MegaCD;;",
	"S0,CUECHD,Insert Disk;",
	"FS6,BINGENMD 32X,Insert Cartridge;",	// MiSTer splits this into THREE-character groups: BIN GEN "MD " 32X
	"O[36],Disc Insert,Reset,Keep Running;",
	"-;",
	"h6O67,Region,Auto(JP),JP,US,EU;",
	"h7O67,Region,Auto(US),JP,US,EU;",
	"h8O67,Region,Auto(EU),JP,US,EU;",
	"-;",
	"O3,Backup RAM,Internal,Internal+Cart;",
	"D0RG,Reload Backup RAM;",
	"D0RH,Save Backup RAM;",
	"D0OD,Autosave,No,Yes;",
	"-;",

	"P1,Audio & Video;",
	"P1-;",
	"P1oHI,Aspect ratio,Original,Full Screen,[ARC1],[ARC2];",
	"P1OU,320x224 Aspect,Original,Corrected;",
	"P1o13,Scandoubler Fx,None,HQ2x,CRT 25%,CRT 50%,CRT 75%;",
	"P1-;",
	"d9P1o0,Vertical Crop,Disabled,216p(5x);",
	"d9P1oJM,Crop Offset,0,2,4,8,10,12,-12,-10,-8,-6,-4,-2;",
	"P1oNO,Scale,Normal,V-Integer,Narrower HV-Integer,Wider HV-Integer;",
	"P1- ;",
	"P1OT,Border,No,Yes;",
	"P1OA,CRAM Dots,Off,On;",
	"P1oFG,Composite Blend,Off,On,Adaptive;",
	"P1OV,Sprite Limit,Normal,High;",
	"P1-;",
	"P1OEF,Audio Filter,Model 1,Model 2,Minimal,No Filter;",
	"P1OR,CD Audio,Unfiltered,Filtered;",
	"P1oPQ,Audio Boost,No,2x,4x;",
	"P1O8,FM Chip,YM2612,YM3438;",
	"P1ON,HiFi PCM,No,Yes;",

	"P2,Input;",
	"P2-;",
	"P2O4,Swap Joysticks,No,Yes;",
	"P2O5,6 Buttons Mode,No,Yes;",
	"P2OLM,Multitap,Disabled,4-Way,TeamPlayer: Port1,TeamPlayer: Port2;",
	"P2-;",
	"P2OIJ,Mouse,None,Port1,Port2;",
	"P2OK,Mouse Flip Y,No,Yes;",
	"P2-;",
	"P2o89,Gun Control,Disabled,Joy1,Joy2,Mouse;",
	"D4P2oA,Gun Fire,Joy,Mouse;",
	"D4P2oBC,Cross,Small,Medium,Big,None;",
	"D4P2oD,Gun Type,Justifier,Menacer;",
	"P2-;",
	"P2oE,Serial,OFF,SNAC;",

	"- ;",
	"H2OB,Enable FM,Yes,No;",//11
	"H2OC,Enable PSG,Yes,No;",//12
	"H2OP,Enable PCM,Yes,No;",//25
	"H2OQ,Enable CDDA,Yes,No;",//26
	"H2O[59],Enable BGA,Yes,No;",
	"H2O[60],Enable BGB,Yes,No;",
	"H2O[61],Enable SPR,Yes,No;",
	"H2O[62],MCD RAM,Banks 2&3,Banks 0&1;",
	"H2O[2],SH2 Clock,23.0MHz,26.8MHz;",
	"H2O[39],MCD /AS,68000,Bus;",
	"H2O[28],MCD PRG DTACK,Data,Early;",
	"H2-;",
	"R[1],Reset;",	// Main rewrites this to status[0] after calling mcd_reset(), so the core sees an
					// ordinary full reset while the disc image is KEPT; "Reset & Eject CD" below is the
					// same bit but Main clears the image first (Main_MiSTer/menu.cpp, is_megacd()).
	"R0,Reset & Eject CD;",
	"R[37],Remove Cartridge & Reset;",
	"R[38],Eject Disc;",
	"J1,A,B,C,Start,Mode,X,Y,Z;",
	"jn,A,B,R,Start,Select,X,Y,L;", // name map to SNES layout.
	"jp,Y,B,A,Start,Select,L,X,R;", // positional map to SNES layout (3 button friendly)  
	"V,v",`BUILD_DATE
};

wire [15:0] status_menumask = {en216p,region,!region,1'b1,!gun_mode,1'b1,~dbg_menu,1'b0,~bk_ena};
wire [63:0] status;
wire  [1:0] buttons;
wire [11:0] joystick_0,joystick_1,joystick_2,joystick_3,joystick_4;
wire  [7:0] joy0_x,joy0_y,joy1_x,joy1_y;
wire        ioctl_download;
wire        ioctl_wr;
wire [24:0] ioctl_addr;
wire [15:0] ioctl_data;
wire  [7:0] ioctl_index;
reg         ioctl_wait;

reg  [31:0] sd_lba[1];
reg         sd_rd = 0;
reg         sd_wr = 0;
wire        sd_ack;
wire  [7:0] sd_buff_addr;
wire [15:0] sd_buff_dout;
wire [15:0] sd_buff_din[1];
wire        sd_buff_wr;
wire        img_mounted;
wire        img_readonly;
wire [63:0] img_size;

wire        forced_scandoubler;
wire [10:0] ps2_key;
wire [24:0] ps2_mouse;

wire [21:0] gamma_bus;

wire [1:0] gun_mode = status[41:40];
wire       gun_btn_mode = status[42];
wire       gun_type = ~status[45];

assign sd_buff_din[0] = sd_lba[0][10:4] ? tmpram_sd_buff_data : bram_sd_buff_data;

hps_io #(.CONF_STR(CONF_STR), .WIDE(1)) hps_io
(
	.clk_sys(clk_sys),
	.HPS_BUS(HPS_BUS),

	.joystick_0(joystick_0),
	.joystick_1(joystick_1),
	.joystick_2(joystick_2),
	.joystick_3(joystick_3),
	.joystick_4(joystick_4),
	.joystick_l_analog_0({joy0_y, joy0_x}),
	.joystick_l_analog_1({joy1_y, joy1_x}),
	.buttons(buttons),
	.forced_scandoubler(forced_scandoubler),
	.new_vmode(new_vmode),

	.status(status),
	.status_in({status[63:8],2'b00,status[5:0]}),
	.status_set(region_reset),
	.status_menumask(status_menumask),

	.ioctl_download(ioctl_download),
	.ioctl_index(ioctl_index),
	.ioctl_wr(ioctl_wr),
	.ioctl_addr(ioctl_addr),
	.ioctl_dout(ioctl_data),
	.ioctl_wait(ioctl_wait),

	.sd_lba(sd_lba),
	.sd_rd(sd_rd),
	.sd_wr(sd_wr),
	.sd_ack(sd_ack),
	.sd_buff_addr(sd_buff_addr),
	.sd_buff_dout(sd_buff_dout),
	.sd_buff_din(sd_buff_din),
	.sd_buff_wr(sd_buff_wr),
	.img_mounted(img_mounted),
	.img_readonly(img_readonly),
	.img_size(img_size),
	
	.gamma_bus(gamma_bus),
	
	.ps2_key(ps2_key),
	.ps2_mouse(ps2_mouse),

	.EXT_BUS(EXT_BUS)
);

wire [35:0] EXT_BUS;
hps_ext hps_ext
(
	.clk_sys(clk_sys),
	.EXT_BUS(EXT_BUS),

	.cd_data_ready(1),
	.cdda_ready(MCD_CDDA_WR_READY),

	.cd_in(cd_in),
	.cd_out(cd_out)
);

reg dbg_menu = 0;
always @(posedge clk_sys) begin
	reg old_stb;
	reg enter = 0;
	reg esc = 0;
	
	old_stb <= ps2_key[10];
	if(old_stb ^ ps2_key[10]) begin
		if(ps2_key[7:0] == 'h5A) enter <= ps2_key[9];
		if(ps2_key[7:0] == 'h76) esc   <= ps2_key[9];
	end
	
	if(enter & esc) begin
		dbg_menu <= ~dbg_menu;
		enter <= 0;
		esc <= 0;
	end
end

wire bios_download = ioctl_download & (ioctl_index[7:6] == 2'b00) & (ioctl_index[5:0] <= 6'h01);
wire cart_download = ioctl_download & ((ioctl_index[5:0] == 6'h06) | ((ioctl_index[7:6] == 2'b01) & (ioctl_index[5:0] <= 6'h01))); // OSD "Insert Cartridge" or cart.rom next to the CD
wire rom_download  = bios_download | cart_download;
wire cart_remove   = status[37];   // OSD "Remove Cartridge & Reset": clears the cart slot and resets, disc kept
wire cdc_dat_download = ioctl_download & (ioctl_index[5:0] == 6'h02);
wire cdc_sub_download = ioctl_download & (ioctl_index[5:0] == 6'h03);
wire cdc_cdda_download = ioctl_download & (ioctl_index[5:0] == 6'h04);
wire save_download = ioctl_download & (ioctl_index[5:0] == 6'h05);

wire reset = RESET | status[0] | cart_remove | buttons[1] | region_set;

///////////////////////////////////////////////////

//Genesis
wire [23:1] GEN_VA;
wire [15:0] GEN_VDI, GEN_VDO;
wire        GEN_RNW, GEN_LDS_N, GEN_UDS_N;
wire        GEN_AS_N, GEN_DTACK_N, GEN_ASEL_N;
wire        GEN_M68K_AS_N;	// the 68000's own /AS: the Mega CD gate array selects Word-RAM data with it
wire        GEN_RAS2_N;
wire        EXT_ROM_N;
wire        EXT_FDC_N;
wire        GEN_VCLK_CE;
wire        GEN_CE0_N;
wire        GEN_LWR_N, GEN_UWR_N, GEN_CAS0_N, GEN_CAS2_N;
wire        GEN_ROM_CE_N;
wire        GEN_PAGE_CE_N;

wire [15:0] GEN_MEM_DO;
wire        GEN_MEM_BUSY;

wire [15:0] GEN_AUDL;
wire [15:0] GEN_AUDR;
wire        GEN_CE;

wire [7:0] color_lut[16] = '{
	8'd0,   8'd27,  8'd49,  8'd71,
	8'd87,  8'd103, 8'd119, 8'd130,
	8'd146, 8'd157, 8'd174, 8'd190,
	8'd206, 8'd228, 8'd255, 8'd255
};

wire [3:0] r, g, b;
wire vs,hs;
wire ce_pix;
wire hblank, vblank;
wire interlace;
wire [1:0] resolution;

wire EN_GEN_FM   = ~status[11] | ~dbg_menu;
wire EN_GEN_PSG  = ~status[12] | ~dbg_menu;
wire EN_MCD_PCM  = ~status[25] | ~dbg_menu;
wire EN_MCD_CDDA = ~status[26] | ~dbg_menu;
wire EN_VDP_BGA  = ~status[59] | ~dbg_menu;
wire EN_VDP_BGB  = ~status[60] | ~dbg_menu;
wire EN_VDP_SPR  = ~status[61] | ~dbg_menu;
wire MCD_BANK23  = ~status[62] | ~dbg_menu;

gen gen
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
	.M68K_AS_O_N(GEN_M68K_AS_N),
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

	// the EXT channel mixes before the console LPF: 32X PWM always (cartridge-port audio in), CD audio when
	// "CD Audio: Filtered" is chosen (otherwise it is added after the LPF below, as upstream did)
	.EXT_SL(ext_l),
	.EXT_SR(ext_r),
	.EN_32X_PWM(1'b1),

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
	.FMBUSY_QUIRK(fmbusy_quirk),

	.RED(r),
	.GREEN(g),
	.BLUE(b),
	.YS_N(YS_N),
	.EDCLK(EDCLK),
	.VS(vs),
	.HS(hs),
	.HBL(hblank),
	.VBL(vblank),
	.CE_PIX(ce_pix),
	.BORDER(status[29]),
	.CRAM_DOTS(status[10]),
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

	.MEM_RDY(1'b0),        // every 000000-7FFFFF access is external here (cartridge or Mega CD) and ends on DTACK;
	                       // MEM_RDY would end the arbiter's ROM read as soon as the SDRAM is idle, before the data is back

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

wire TRANSP_DETECT = 0; // the SystemVerilog VDP has no transparency detect; "Adaptive" blend = Off
wire cofi_enable = status[47] || (status[48] && TRANSP_DETECT);

// The 32X sits in the cartridge slot: everything on /CE0, /TIME and its own windows comes back through it
// (cart.sv answers behind it on the pass-through bus); the Mega CD is on the expansion port.
// Select the source by ADDRESS, not by the 32X's /DTACK. Keying off ~S32X_DTACK_N means that if the 32X
// ever asserts DTACK outside its own cycle - the audit found MD_ROM_WAIT can be latched and left set,
// letting the ROM arbiter run a phantom cycle later - it hijacks whatever read is in flight, including a
// Mega CD one. The Mega CD owns exactly its three decoded windows; everything else is the cartridge side.
wire        mcd_window = ~EXT_ROM_N | ~GEN_RAS2_N | ~EXT_FDC_N;
assign GEN_VDI = mcd_window ? MCD_DO : S32X_VDO;
assign GEN_DTACK_N = MCD_DTACK_N & S32X_DTACK_N & CART_DTACK_N;


// MCD
wire [15:0] MCD_DO;
wire        MCD_DTACK_N;

wire [15:0] MCD_PCM_SL;
wire [15:0] MCD_PCM_SR;
wire [15:0] MCD_CDDA_SL;
wire [15:0] MCD_CDDA_SR;
wire        MCD_CDDA_WR_READY;

wire [17:0] MCD_PRG_ADDR;
wire [15:0] MCD_PRG_DO;
wire [15:0] MCD_PRG_DI;
wire        MCD_PRG_OE_N;
wire        MCD_PRG_WRL_N;
wire        MCD_PRG_WRH_N;
wire        MCD_PRG_BUSY;

wire [13:1] MCD_BRAM_ADDR;
wire  [7:0] MCD_BRAM_DO;
wire  [7:0] MCD_BRAM_DI;
wire        MCD_BRAM_WE;

wire        MCD_LED_RED;
wire        MCD_LED_GREEN;

wire        MCD_RST_N;

wire [15:0] MCD_PCMRAM_A;
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
(
	.RST_N(~(reset|rom_download)),
	.CLK(clk_sys),
	.ENABLE(1),
	.EN50(mcd_en),
	.MCD_RST_N(MCD_RST_N),
	.PALSW(PAL),

	.EXT_VA(GEN_VA[17:1]),
	.EXT_VDI(GEN_VDO),
	.EXT_VDO(MCD_DO),
	// Which strobe the gate array latches Word RAM data with. MEASURED on hardware, A/B'd live on the
	// Mega CD BIOS: the 68000's own /AS renders the SEGA and MEGA-CD logos cleanly and matches
	// upstream, while the bus arbiter's /AS garbles both into blocks. Reasoning from the bus
	// protocol had suggested the arbiter's, since /AS is driven by whichever master owns the bus;
	// the measurement says otherwise and the measurement wins. Debug bit 39 selects the arbiter's
	// for comparison. See tools/phase11_as_select.py.
	.EXT_AS_N(status[39] ? GEN_AS_N : GEN_M68K_AS_N),
	.EXT_RNW(GEN_RNW),
	.EXT_LDS_N(GEN_LDS_N),
	.EXT_UDS_N(GEN_UDS_N),
	.EXT_DTACK_N(MCD_DTACK_N),
	.EXT_ASEL_N(GEN_ASEL_N),
	.EXT_VCLK_CE(GEN_VCLK_CE),
	.EXT_RAS2_N(GEN_RAS2_N),
	.EXT_ROM_N(EXT_ROM_N),
	.EXT_FDC_N(EXT_FDC_N),

	.PRG_A(MCD_PRG_ADDR),
	.PRG_DI(MCD_PRG_DI),
	.PRG_DO(MCD_PRG_DO),
	.PRG_WRL_N(MCD_PRG_WRL_N),
	.PRG_WRH_N(MCD_PRG_WRH_N),
	.PRG_OE_N(MCD_PRG_OE_N),
	.PRG_RDY(~MCD_PRG_BUSY),
	.DBG_EARLY_DTACK(status[28] & dbg_menu),

	.DBG_S68K_AS_N(MCD_DBG_AS_N),
	.DBG_S68K_DTACK_N(MCD_DBG_DTACK_N),
	.DBG_S68K_RNW(MCD_DBG_RNW),
	.DBG_S68K_A(MCD_DBG_A),
	
	.ROM_DI(GEN_MEM_DO),
	.ROM_CE_N(GEN_ROM_CE_N),
	.ROM_RDY(~GEN_MEM_BUSY),
	
	.BRAM_A(MCD_BRAM_ADDR),
	.BRAM_DI(MCD_BRAM_DI),
	.BRAM_DO(MCD_BRAM_DO),
	.BRAM_WE(MCD_BRAM_WE),
	
	.CDD_STAT(scd_cdd_stat),
	.CDD_COMM(scd_cdd_comm),
	.CDD_SEND(scd_cdd_send),
	.CDD_REC(scd_cdd_rec),
	.CDD_DM(scd_cdd_dm),
	
	.CDC_DATA(cdc_d),
	.CDC_DAT_WR(cdc_wr & (cdc_dat_download | cdc_cdda_download)),
	.CDC_SC_WR(cdc_wr & cdc_sub_download),
	.CDC_CDDA_WR(cdc_wr & cdc_cdda_download),
	.CDDA_WR_READY(MCD_CDDA_WR_READY),

	.PCMRAM_A(MCD_PCMRAM_A),
	.PCMRAM_DO(MCD_PCMRAM_DO),
	.PCMRAM_DI(MCD_PCMRAM_DI[7:0]),
	.PCMRAM_RD(MCD_PCMRAM_RD),
	.PCMRAM_WR(MCD_PCMRAM_WR),
	.PCMRAM_BUSY(MCD_PCMRAM_BUSY),

	.PCM_SL(MCD_PCM_SL),
	.PCM_SR(MCD_PCM_SR),
	.CDDA_SL(MCD_CDDA_SL),
	.CDDA_SR(MCD_CDDA_SR),
	
	.LED_RED(MCD_LED_RED),
	.LED_GREEN(MCD_LED_GREEN)
);

localparam [3:0] comp_f1 = 4;
localparam [3:0] comp_a1 = 2;
localparam       comp_x1 = ((32767 * (comp_f1 - 1)) / ((comp_f1 * comp_a1) - 1)) + 1; // +1 to make sure it won't overflow
localparam       comp_b1 = comp_x1 * comp_a1;

localparam [3:0] comp_f2 = 8;
localparam [3:0] comp_a2 = 4;
localparam       comp_x2 = ((32767 * (comp_f2 - 1)) / ((comp_f2 * comp_a2) - 1)) + 1; // +1 to make sure it won't overflow
localparam       comp_b2 = comp_x2 * comp_a2;

function [15:0] compr; input [15:0] inp;
	reg [15:0] v, v1, v2;
	begin
		v  = inp[15] ? (~inp) + 1'd1 : inp;
		v1 = (v < comp_x1[15:0]) ? (v * comp_a1) : (((v - comp_x1[15:0])/comp_f1) + comp_b1[15:0]);
		v2 = (v < comp_x2[15:0]) ? (v * comp_a2) : (((v - comp_x2[15:0])/comp_f2) + comp_b2[15:0]);
		v  = status[58] ? v2 : v1;
		compr = inp[15] ? ~(v-1'd1) : v;
	end
endfunction

function [15:0] sat16(input [16:0] v);   // saturating 17 -> 16 bit
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

	if(~status[27]) begin
		aud_l <= {GEN_AUDL[15],GEN_AUDL[15:1]} + {mcd_l[15],mcd_l[15:1]};
		aud_r <= {GEN_AUDR[15],GEN_AUDR[15:1]} + {mcd_r[15],mcd_r[15:1]};
	end
	else begin
		aud_l <= GEN_AUDL;
		aud_r <= GEN_AUDR;
	end
	
	cmp_l <= compr(aud_l);
	cmp_r <= compr(aud_r);
end

// Audio telemetry: sticky peak of each point in the mix plus a sample-enable count, so a silent tier
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
wire [63:0] tel_mcdbus = {tel_lat_min, tel_lat_max, tel_lat_slow, tel_lat_n};

audio_fix #(250) audio_fix // MCLK/504 in lpf, so choose half to get in the middle of sample period
(
	.*,
	.clk(clk_sys),
	.ce(GEN_CE),
	.l(status[58:57] ? cmp_l : aud_l),
	.r(status[58:57] ? cmp_r : aud_r)
);

//////////////////////////////////////////////////////////////////
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

S32X #(.USE_ROM_WAIT(1)) S32X
(
	.CLK(clk_sys),
	.RST_N(~(reset | rom_download)),
	.SH2_DIV2(status[2]),

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

// NOTE (deferred): the cartridge SDRAM port is driven straight from cart.sv's combinational decode; the
// clk_ram -> clk_sys crossing shows as a timing failure (see HANDOFF) but works. Re-registering it broke the
// boot, so it waits for the corruption/timing pass.

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
	.lb_q(S32X_LB_Q),

	.tel_audio(tel_audio),
	.tel_mcdbus(tel_mcdbus)
);

always @(posedge clk_sys) begin
	reg old_busy;
	
	old_busy <= tmpram_busy;
	if(rom_download & ioctl_wr) ioctl_wait <= 1;
	if(old_busy & ~tmpram_busy) ioctl_wait <= 0;
end

assign MCD_PRG_BUSY = sdr_busy;
assign MCD_PRG_DI   = sdr_do;


//MCD PRGRAM, GEN ROM/RAM/CART RAM
wire sdr_busy;
wire [15:0] sdr_do;
sdram sdram
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


wire [15:0] bram_sd_buff_data;
dpram_dif #(13,8,12,16) bram
(
	.clock(clk_sys),
	.address_a(MCD_BRAM_ADDR),
	.data_a(MCD_BRAM_DO),
	.wren_a(MCD_BRAM_WE),
	.q_a(MCD_BRAM_DI),

	.address_b({sd_lba[0][3:0],sd_buff_addr}),
	.data_b(sd_buff_dout),
	.wren_b(sd_buff_wr & sd_ack & !sd_lba[0][10:4]),
	.q_b(bram_sd_buff_data)
);

wire [7:0] tmpram_dout;
wire [7:0] tmpram_din;
wire       tmpram_busy;

wire [15:0] tmpram_sd_buff_data;
dpram_dif #(9,8,8,16) tmpram
(
	.clock(clk_sys),

	.address_a(tmpram_addr),
	.wren_a(~bk_loading & tmpram_busy_d & ~tmpram_busy),
	.data_a(tmpram_din),
	.q_a(tmpram_dout),

	.address_b(sd_buff_addr),
	.wren_b(sd_buff_wr & sd_ack & |sd_lba[0][10:4]),
	.data_b(sd_buff_dout),
	.q_b(tmpram_sd_buff_data)
);

reg [10:0] tmpram_lba;
reg  [8:0] tmpram_addr;
reg tmpram_tx_start;
reg tmpram_tx_finish;
reg tmpram_req;
reg tmpram_busy_d;
always @(posedge clk_sys) begin
	reg state;

	tmpram_lba <= sd_lba[0][10:0]-11'h10;
	
	tmpram_busy_d <= tmpram_busy;
	if(~tmpram_busy_d & tmpram_busy) tmpram_req <= 0;

	if(~tmpram_tx_start) {tmpram_addr, state, tmpram_tx_finish} <= 0;
	else if(~tmpram_tx_finish) begin
		if(!state) begin
			tmpram_req <= 1;
			state <= 1;
		end
		else if(tmpram_busy_d & ~tmpram_busy) begin
			state <= 0;
			if(~&tmpram_addr) tmpram_addr <= tmpram_addr + 1'd1;
			else tmpram_tx_finish <= 1;
		end
	end
end


//CD communication
reg [48:0] cd_in;
wire [48:0] cd_out;

reg [39:0] scd_cdd_stat;
reg scd_cdd_dm;
wire [39:0] scd_cdd_comm;
wire scd_cdd_send;
reg scd_cdd_rec;

always @(posedge clk_sys) begin
	reg cd_out48_last = 1;
	reg scd_cdd_send_old = 0;
	reg [2:0] cnt = 0;
	reg rst_old = 0;
	
	if (cd_out[48] != cd_out48_last)  begin
		cd_out48_last <= cd_out[48];
		scd_cdd_stat <= cd_out[39:0];
		scd_cdd_dm <= cd_out[40];
		scd_cdd_rec <= 1;
		cnt <= 7;
	end
	else if (cnt) begin
		cnt <= cnt - 1'd1;
	end
	else begin
		scd_cdd_rec <= 0;
	end
	
	scd_cdd_send_old <= scd_cdd_send;
	if (scd_cdd_send && !scd_cdd_send_old) begin
		cd_in[47:0] <= {8'h00,scd_cdd_comm};
		cd_in[48] <= ~cd_in[48];
	end
	else begin
		rst_old <= MCD_RST_N;
		if (rst_old & ~MCD_RST_N) begin
			cd_in[47:0] <= 8'hFF;
			cd_in[48] <= ~cd_in[48];
		end
	end
end


//extend cdc_wr for 8 cycles
reg  cdc_wr;
reg [15:0] cdc_d;
always @(posedge clk_sys) begin
	reg [2:0] cnt = 0;

	if (ioctl_wr) begin
		cnt <= 7;
		cdc_wr <= 1;
		cdc_d <= ioctl_data;
	end
	else if (cnt) begin
		cnt <= cnt - 1'd1;
	end
	else begin
		cdc_wr <= 0;
	end
end


/////////////////////////////////////////////////////////////
wire PAL = region[1];

reg new_vmode;
always @(posedge clk_sys) begin
	reg old_pal;
	int to;
	
	if(~(reset | rom_download)) begin
		old_pal <= PAL;
		if(old_pal != PAL) to <= 5000000;
	end
	else to <= 5000000;
	
	if(to) begin
		to <= to - 1;
		if(to == 1) new_vmode <= ~new_vmode;
	end
end

//lock resolution for the whole frame.
reg [1:0] res;
always @(posedge clk_sys) begin
	reg old_vbl;
	
	old_vbl <= vblank;
	if(old_vbl & ~vblank) res <= resolution;
end

wire [2:0] scale = status[35:33];
wire [2:0] sl = scale ? scale - 1'd1 : 3'd0;

assign CLK_VIDEO = clk_ram;
assign VGA_SL = {~interlace,~interlace}&sl[1:0];

reg old_ce_pix;
always @(posedge CLK_VIDEO) old_ce_pix <= ce_pix;

wire [7:0] red, green, blue;

cofi coffee (
	.clk(clk_sys),
	.pix_ce(ce_pix),
	.enable(cofi_enable),

	.hblank(hblank),
	.vblank(vblank),
	.hs(hs),
	.vs(vs),
	.red(vid_r),
	.green(vid_g),
	.blue(vid_b),

	.hblank_out(hblank_c),
	.vblank_out(vblank_c),
	.hs_out(hs_c),
	.vs_out(vs_c),
	.red_out(red),
	.green_out(green),
	.blue_out(blue)
);

wire hs_c,vs_c,hblank_c,vblank_c;

// 32X overlay: the 32X VDP's pixel replaces the MD's where it is active (YSO_N low), as on the real stack
wire        EN_32X_VID = ~status[9] | ~dbg_menu;
wire        s32x_pix = ~S32X_YSO_N & EN_32X_VID;
wire  [7:0] vid_r = s32x_pix ? {S32X_R, S32X_R[4:2]} : color_lut[r];
wire  [7:0] vid_g = s32x_pix ? {S32X_G, S32X_G[4:2]} : color_lut[g];
wire  [7:0] vid_b = s32x_pix ? {S32X_B, S32X_B[4:2]} : color_lut[b];

video_mixer #(.LINE_LENGTH(320), .HALF_DEPTH(0), .GAMMA(1)) video_mixer
(
	.*,

	.ce_pix(~old_ce_pix & ce_pix),

	.scandoubler(~interlace && (scale || forced_scandoubler)),
	.hq2x(scale==1),
	.freeze_sync(),

	.VGA_DE(vga_de),
	.R((lg_target && gun_mode && (~&status[44:43])) ? {8{lg_target[0]}} : red),
	.G((lg_target && gun_mode && (~&status[44:43])) ? {8{lg_target[1]}} : green),
	.B((lg_target && gun_mode && (~&status[44:43])) ? {8{lg_target[2]}} : blue),

	// Positive pulses.
	.HSync(hs_c),
	.VSync(vs_c),
	.HBlank(hblank_c),
	.VBlank(vblank_c)
);

wire [2:0] lg_target;
wire       lg_sensor;
wire       lg_a;
wire       lg_b;
wire       lg_c;
wire       lg_start;

lightgun lightgun
(
	.CLK(clk_sys),
	.RESET(reset),

	.MOUSE(ps2_mouse),
	.MOUSE_XY(&gun_mode),

	.JOY_X(gun_mode[0] ? joy0_x : joy1_x),
	.JOY_Y(gun_mode[0] ? joy0_y : joy1_y),
	.JOY(gun_mode[0] ? joystick_0 : joystick_1),

	.RELOAD(gun_type),

	.HDE(~hblank_c),
	.VDE(~vblank_c),
	.CE_PIX(ce_pix),
	.H40(res[0]),

	.BTN_MODE(gun_btn_mode),
	.SIZE(status[44:43]),
	.SENSOR_DELAY(gun_type ? 8'd32 : 8'd64),

	.TARGET(lg_target),
	.SENSOR(lg_sensor),
	.BTN_A(lg_a),
	.BTN_B(lg_b),
	.BTN_C(lg_c),
	.BTN_START(lg_start)
);

reg  [1:0] region_req;
reg        region_reset;
wire       pressed = ps2_key[9];
wire [8:0] code    = ps2_key[8:0];
always @(posedge clk_sys) begin
	reg old_state = 0;

	if(reset) region_reset <= 0;

	old_state <= ps2_key[10];
	if(old_state != ps2_key[10]) begin
		casex(code)
			'h005: begin region_req <= 0; region_reset <= pressed; end // F1
			'h006: begin region_req <= 1; region_reset <= pressed; end // F2
			'h004: begin region_req <= 2; region_reset <= pressed; end // F3
		endcase
	end

	if(ioctl_wr & bios_download) begin // BIOS download only: a cartridge cannot change the console's region
		if(ioctl_addr == 'h1F0) begin
			if(ioctl_data[7:0] == "J") region_req <= 0;
			else if(ioctl_data[7:0] == "U") region_req <= 1;
			else region_req <= 2;
		end
	end
end

wire [1:0] region_new = status[7:6] ? (status[7:6] - 1'd1) : region_req;

reg  [1:0] region;
reg        region_set = 0;
always @(posedge clk_sys) begin
	reg [15:0] to = 0;
	
	region <= region_new;
	if(region != region_new) to <= 0;
	
	region_set <= 0;
	if(~&to) begin
		to <= to + 1'd1;
		region_set <= 1;
	end
end


/////////////////////////  BRAM SAVE/LOAD  /////////////////////////////

wire downloading = save_download;
wire bk_change  = MCD_BRAM_WE | (CART_EN & CART_SRAM_WR);
wire autosave   = status[13];
wire bk_load    = status[16];
wire bk_save    = status[17];

reg bk_ena = 0;
reg sav_pending = 0;
always @(posedge clk_sys) begin
	reg old_downloading = 0;
	reg old_change = 0;

	old_downloading <= downloading;
	if(~old_downloading & downloading) bk_ena <= 0;

	//Save file always mounted in the end of downloading state.
	if(downloading && img_mounted && !img_readonly) bk_ena <= 1;

	old_change <= bk_change;
	if (~old_change & bk_change) sav_pending <= 1;
	else if (bk_state) sav_pending <= 0;
end

wire bk_save_a  = autosave & OSD_STATUS;
reg  bk_loading = 0;
reg  bk_state   = 0;
reg  bk_reload  = 0;

always @(posedge clk_sys) begin
	reg old_downloading = 0;
	reg old_load = 0, old_save = 0, old_save_a = 0, old_ack;
	reg [1:0] state;

	old_downloading <= downloading;

	old_load   <= bk_load;
	old_save   <= bk_save;
	old_save_a <= bk_save_a;
	old_ack    <= sd_ack;

	if(~old_ack & sd_ack) {sd_rd, sd_wr} <= 0;

	if(!bk_state) begin
		tmpram_tx_start <= 0;
		state <= 0;
		sd_lba[0] <= 0;
		bk_reload <= 0;
		bk_loading <= 0;
		if(bk_ena & ((~old_load & bk_load) | (~old_save & bk_save) | (~old_save_a & bk_save_a & sav_pending))) begin
			bk_state <= 1;
			bk_loading <= bk_load;
			bk_reload <= bk_load;
			sd_rd <=  bk_load;
			sd_wr <= ~bk_load;
		end
		if(old_downloading & ~rom_download & bk_ena) begin
			bk_state <= 1;
			bk_loading <= 1;
			sd_rd <= 1;
			sd_wr <= 0;
		end
	end
	else if(!sd_lba[0][10:4]) begin
		if(old_ack & ~sd_ack) begin
			sd_lba[0] <= sd_lba[0] + 1'd1;
			if(&sd_lba[0][3:0]) begin
				if(~CART_EN) bk_state <= 0;
			end else begin
				sd_rd <=  bk_loading;
				sd_wr <= ~bk_loading;
			end
		end
	end
	else if(bk_loading) begin
		case(state)
			0: begin
					sd_rd <= 1;
					state <= 1;
				end
			1: if(old_ack & ~sd_ack) begin
					tmpram_tx_start <= 1;
					state <= 2;
				end
			2: if(tmpram_tx_finish) begin
					tmpram_tx_start <= 0;
					state <= 0;
					sd_lba[0] <= sd_lba[0] + 1'd1;
					if(sd_lba[0][10:0] == 11'h40F) bk_state <= 0;
				end
		endcase
	end
	else begin
		case(state)
			0: begin
					tmpram_tx_start <= 1;
					state <= 1;
				end
			1: if(tmpram_tx_finish) begin
					tmpram_tx_start <= 0;
					sd_wr <= 1;
					state <= 2;
				end
			2: if(old_ack & ~sd_ack) begin
					state <= 0;
					sd_lba[0] <= sd_lba[0] + 1'd1;
					if(sd_lba[0][10:0] == 11'h40F) bk_state <= 0;
				end
		endcase
	end
end

wire [7:0] SERJOYSTICK_IN;
wire [7:0] SERJOYSTICK_OUT;
wire [1:0] SER_OPT;

always @(posedge clk_sys) begin
	if (status[46]) begin
		SERJOYSTICK_IN[0] <= USER_IN[1];//up
		SERJOYSTICK_IN[1] <= USER_IN[0];//down	
		SERJOYSTICK_IN[2] <= USER_IN[5];//left	
		SERJOYSTICK_IN[3] <= USER_IN[3];//right
		SERJOYSTICK_IN[4] <= USER_IN[2];//b TL		
		SERJOYSTICK_IN[5] <= USER_IN[6];//c TR GPIO7			
		SERJOYSTICK_IN[6] <= USER_IN[4];//  TH
		SERJOYSTICK_IN[7] <= 0;
		SER_OPT[0] <= ~status[4];
		SER_OPT[1] <= status[4];
		USER_OUT[1] <= SERJOYSTICK_OUT[0];
		USER_OUT[0] <= SERJOYSTICK_OUT[1];
		USER_OUT[5] <= SERJOYSTICK_OUT[2];
		USER_OUT[3] <= SERJOYSTICK_OUT[3];
		USER_OUT[2] <= SERJOYSTICK_OUT[4];
		USER_OUT[6] <= SERJOYSTICK_OUT[5];
		USER_OUT[4] <= SERJOYSTICK_OUT[6];
	end else begin
		SER_OPT  <= 0;
		USER_OUT <= '1;
	end
end


///////////////////////////////////////////////

reg         rom_cart_mode = 0;
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
end

endmodule
