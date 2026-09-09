#!/usr/bin/env python3
"""Phase 2 step 2 (after phase2_top_edit.py): clock-domain hygiene on the cartridge SDRAM port.
The SDRAM controller runs on clk_ram (107 MHz). Its read data reached the 32X interface's negedge samplers and
the MD (Z80/68000/VDP data inputs) through cart.sv's and the 32X's combinational muxes (-8.9 ns / -1.3 ns), and
the SH-2's address reached the controller's request logic through the same muxes (-0.5 ns). Register the port
both ways in clk_sys: requests (address/data/strobes from cart.sv) and results (data/busy). The 32X's ROM state
machine waits for busy to rise and fall, so a one-clock delay each way is invisible to it.
Usage: phase2_top_edit2.py <core/MegaCD.sv>"""
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8", errors="replace").read()

def rep(old, new):
    global s
    assert old in s, "anchor missing: " + old[:70]
    s = s.replace(old, new, 1)

rep("""wire [15:0] CART_MEM_DO;
wire        CART_MEM_BUSY;
wire        CART_SRAM_ACC = CART_SRAM_RD | CART_SRAM_WR;
wire        CART_EXT = CART_ROM_RD | CART_ROM_WRL | CART_ROM_WRH | CART_SRAM_ACC;
""", """wire [15:0] CART_MEM_DO;         // clk_sys-registered SDRAM port 0 read data
wire        CART_MEM_BUSY;       // clk_sys-registered SDRAM port 0 busy
wire        CART_SRAM_ACC = CART_SRAM_RD | CART_SRAM_WR;
wire        CART_EXT = CART_ROM_RD | CART_ROM_WRL | CART_ROM_WRH | CART_SRAM_ACC;

// SDRAM port 0 is on clk_ram: register the request (from cart.sv's combinational decode of the 32X's
// pass-through strobes) and the result (data, busy) in clk_sys so no path crosses the domains through
// the cart/32X muxes. The 32X waits for busy to rise then fall, so the extra clock each way is invisible.
reg  [24:1] cm_addr;
reg  [15:0] cm_din;
reg         cm_rd, cm_wrl, cm_wrh;
wire [15:0] cm_dout;
wire        cm_busy;
reg  [15:0] cm_dout_r;
reg         cm_busy_r, cm_pend;
always @(posedge clk_sys) begin
	reg old_req;
	cm_addr   <= CART_SRAM_ACC ? {9'b011100000, CART_SRAM_A[14:0]} : {1'b0, CART_ROM_A[23:1]};
	cm_din    <= CART_SRAM_ACC ? {8'h00, CART_SRAM_DO} : CART_ROM_DO;
	cm_rd     <= CART_ROM_RD | CART_SRAM_RD;
	cm_wrl    <= CART_ROM_WRL | CART_SRAM_WR;
	cm_wrh    <= CART_ROM_WRH;
	cm_busy_r <= cm_busy;
	if (cm_busy_r & ~cm_busy) cm_dout_r <= cm_dout;   // the controller's data is final when busy drops
	// a new request (rising strobe) counts as busy until the controller's busy is seen, so the 32X never
	// samples the gap between issuing the request and the controller accepting it
	old_req <= cm_rd | cm_wrl | cm_wrh;
	if ((cm_rd | cm_wrl | cm_wrh) & ~old_req) cm_pend <= 1;
	else if (cm_busy_r) cm_pend <= 0;
end
assign CART_MEM_DO   = cm_dout_r;
assign CART_MEM_BUSY = cm_busy_r | cm_pend;
""")
rep("""	// cartridge (MD or SH-2 through the 32X): ROM 0000000-0DFFFFF, SRAM 0E00000-0EFFFFF (one byte per word, low lane)
	.addr0(CART_SRAM_ACC ? {9'b011100000, CART_SRAM_A[14:0]} : {1'b0, CART_ROM_A[23:1]}),
	.din0(CART_SRAM_ACC ? {8'h00, CART_SRAM_DO} : CART_ROM_DO),
	.dout0(CART_MEM_DO),
	.rd0(CART_ROM_RD | CART_SRAM_RD),
	.wrl0(CART_ROM_WRL | CART_SRAM_WR),
	.wrh0(CART_ROM_WRH),
	.busy0(CART_MEM_BUSY),
""", """	// cartridge (MD or SH-2 through the 32X): ROM 0000000-0DFFFFF, SRAM 0E00000-0EFFFFF (one byte per word, low lane)
	.addr0(cm_addr),
	.din0(cm_din),
	.dout0(cm_dout),
	.rd0(cm_rd),
	.wrl0(cm_wrl),
	.wrh0(cm_wrh),
	.busy0(cm_busy),
""")
open(p, "w", encoding="utf-8").write(s)
print("ok")
