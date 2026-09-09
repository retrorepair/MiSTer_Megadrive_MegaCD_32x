#!/usr/bin/env python3
"""Phase 1, step 2 (applied after phase1_top_edit.py):
 - ROM reads wait for the external DTACK (MEM_RDY tied low): the Mega CD BIOS path and CART.vhd answer with DTACK,
   and the new bus arbiter otherwise ends a ROM read as soon as the SDRAM happens to be idle (stale data: corrupt BIOS logo).
 - Cartridge slot handling from the NukedMD-MegaCD project, matching the retrorepair Main fork:
   index 6 = OSD "Insert Cartridge", 40/41 = cart.rom next to the CD, R[37] Remove Cartridge & Reset,
   R[38] Eject Disc (Main-side), O[36] Disc Insert Reset/Keep Running (Main-side). The debug-menu bits move
   from 36-39 to 59-62 so Main's [36] read is not aliased.
Usage: phase1_top_edit2.py <core/MegaCD.sv>"""
import re, sys
p = sys.argv[1]
s = open(p, encoding="utf-8", errors="replace").read()

def rep(old, new):
    global s
    assert old in s, "anchor missing: " + old[:70]
    s = s.replace(old, new, 1)

# 1. ROM reads complete on DTACK only
rep("\t.MEM_RDY(~GEN_MEM_BUSY),",
    "\t.MEM_RDY(1'b0),        // every 000000-7FFFFF access is external here (cartridge or Mega CD) and ends on DTACK;\n"
    "\t                       // MEM_RDY would end the arbiter's ROM read as soon as the SDRAM is idle, before the data is back")

# 2. download decode
rep("wire rom_download = ioctl_download & (ioctl_index[5:0] <= 6'h01);\n",
    """wire bios_download = ioctl_download & (ioctl_index[7:6] == 2'b00) & (ioctl_index[5:0] <= 6'h01);
wire cart_download = ioctl_download & ((ioctl_index[5:0] == 6'h06) | ((ioctl_index[7:6] == 2'b01) & (ioctl_index[5:0] <= 6'h01))); // OSD "Insert Cartridge" or cart.rom next to the CD
wire rom_download  = bios_download | cart_download;
wire cart_remove   = status[37];   // OSD "Remove Cartridge & Reset": clears the cart slot and resets, disc kept
""")
rep("wire reset = RESET | status[0] | buttons[1] | region_set;",
    "wire reset = RESET | status[0] | cart_remove | buttons[1] | region_set;")

# 3. OSD media entries (bracket syntax) and debug bits moved to 59-62
rep('\t"S0,CUECHD,Insert Disk;",\n\t"-;",\n',
    '\t"S0,CUECHD,Insert Disk;",\n\t"FS6,BINGENMD,Insert Cartridge;",\n\t"O[36],Disc Insert,Reset,Keep Running;",\n\t"-;",\n')
rep('\t"H2o4,Enable BGA,Yes,No;",//36\n\t"H2o5,Enable BGB,Yes,No;",//37\n\t"H2o6,Enable SPR,Yes,No;",//38\n\t"H2o7,MCD RAM,Banks 2&3,Banks 0&1;",//39\n',
    '\t"H2O[59],Enable BGA,Yes,No;",\n\t"H2O[60],Enable BGB,Yes,No;",\n\t"H2O[61],Enable SPR,Yes,No;",\n\t"H2O[62],MCD RAM,Banks 2&3,Banks 0&1;",\n')
rep('\t"R0,Reset & Eject CD;",\n',
    '\t"R0,Reset & Eject CD;",\n\t"R[37],Remove Cartridge & Reset;",\n\t"R[38],Eject Disc;",\n')
rep("wire EN_VDP_BGA  = ~status[36] | ~dbg_menu;\nwire EN_VDP_BGB  = ~status[37] | ~dbg_menu;\nwire EN_VDP_SPR  = ~status[38] | ~dbg_menu;\nwire MCD_BANK23  = ~status[39] | ~dbg_menu;",
    "wire EN_VDP_BGA  = ~status[59] | ~dbg_menu;\nwire EN_VDP_BGB  = ~status[60] | ~dbg_menu;\nwire EN_VDP_SPR  = ~status[61] | ~dbg_menu;\nwire MCD_BANK23  = ~status[62] | ~dbg_menu;")

# 4. cartridge-in-slot state (physical: survives reset and disc change; only "Remove Cartridge" clears a manual one,
#    a cart.rom-beside-the-CD one is dropped when the next BIOS/game loads)
rep("""reg [23:13] rom_mask;
reg         rom_cart_mode;
always @(posedge clk_sys) begin
	if (rom_download & ioctl_wr) begin
		rom_cart_mode <= ioctl_index[6];
		if (ioctl_index[6]) begin
			rom_mask <= rom_mask | ioctl_addr[23:13];
			if(!ioctl_addr) rom_mask <= 0;
		end
	end
end""",
"""reg [23:13] rom_mask;
reg         rom_cart_mode = 0;
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
end""")
rep("\tif(ioctl_wr & rom_download & ioctl_index[6]) begin\n\t\tif(ioctl_addr == 'h182)",
    "\tif(ioctl_wr & cart_download) begin\n\t\tif(ioctl_addr == 'h182)")
rep("\tif(ioctl_wr & rom_download & ~ioctl_index[6]) begin // BIOS download only: a cartridge cannot change the console's region",
    "\tif(ioctl_wr & bios_download) begin // BIOS download only: a cartridge cannot change the console's region")
rep("\t.addr3( rom_download ? (rom_cart_mode ? {2'b00,ioctl_addr[22:1]} : {6'b011110,ioctl_addr[18:1]}) :",
    "\t.addr3( rom_download ? (cart_download ? {2'b00,ioctl_addr[22:1]} : {6'b011110,ioctl_addr[18:1]}) :")

open(p, "w", encoding="utf-8").write(s)
print("ok")
