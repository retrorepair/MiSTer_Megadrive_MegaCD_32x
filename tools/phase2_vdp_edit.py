#!/usr/bin/env python3
"""Phase 2: move the 32X VDP's frame buffers off-chip (rtl/s32x_ddr.sv).
The VDP keeps its two internal streams; only their memory side changes:
 - display: the line-table entry and the line's words come from the line buffer that s32x_ddr
   prefetched during the previous HBLANK (LP_REQ at H_CNT 0x1D0, LP_START/LP_BASE, LB_ADDR/LB_Q);
 - draw: FBD_* port with FBD_BUSY (write FIFO nearly full) and FBD_RDY (read data back).
Usage: phase2_vdp_edit.py <core/rtl/S32X/VDP.sv>"""
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8", errors="replace").read()
s = "\n".join(l.rstrip() for l in s.replace("\r\n", "\n").split("\n"))  # normalise CRLF / trailing whitespace

def rep(old, new):
    global s
    assert old in s, "anchor missing: " + old[:70]
    s = s.replace(old, new, 1)

rep("module S32X_VDP\n#(parameter bit USE_ASYNC_FB=1)\n(", "module S32X_VDP\n(")
rep("""	output     [15:0] FB0_A,
	input      [15:0] FB0_DI,
	output     [15:0] FB0_DO,
	output      [1:0] FB0_WE,
	output            FB0_RD,

	output     [15:0] FB1_A,
	input      [15:0] FB1_DI,
	output     [15:0] FB1_DO,
	output      [1:0] FB1_WE,
	output            FB1_RD,
""", """	// frame-buffer draw port (rtl/s32x_ddr.sv)
	output            FBD_FB,		// buffer being drawn (= ~FS)
	output     [15:0] FBD_A,
	output     [15:0] FBD_DO,
	output      [1:0] FBD_WE,
	output            FBD_RD,
	input      [15:0] FBD_DI,
	input             FBD_BUSY,
	input             FBD_RDY,

	// display line prefetch and line buffer (rtl/s32x_ddr.sv)
	output            LP_REQ,
	output            LP_FB,		// buffer being displayed (= FS)
	output      [7:0] LP_LINE,
	input      [15:0] LP_START,
	input      [15:0] LP_BASE,
	output      [8:0] LB_ADDR,
	input      [15:0] LB_Q,
""")

rep("""	bit        FB_WR;
	bit        FB_RD;

	bit [15:0] FB_DRAW_A;
	bit [15:0] FB_DRAW_D;
	bit  [1:0] FB_DRAW_WE;
	bit        FB_DRAW_RD;
	bit [15:0] FB_DRAW_Q;

	bit [15:0] FB_DISP_A;
	bit        FB_DISP_RD;
	bit [15:0] FB_DISP_Q;
""", """	bit        FB_WR;
	bit        FB_RD;
	bit        FB_RD_WAIT;

	bit [15:0] FB_DRAW_A;
	bit [15:0] FB_DRAW_D;
	bit  [1:0] FB_DRAW_WE;
	bit        FB_DRAW_RD;
""")

# draw-side read: request once, acknowledge when the DDR3 port answers
rep("""			ACK_N <= 1;
			FILL_PEND <= 0;
			FILL_EXEC <= 0;
			FILL_CNT <= '0;
			PAL_ACCESS <= 0;
			ACCESS_WAIT <= 3'd7;
			FILL_WAIT <= '0;""", """			ACK_N <= 1;
			FILL_PEND <= 0;
			FILL_EXEC <= 0;
			FILL_CNT <= '0;
			PAL_ACCESS <= 0;
			FILL_WAIT <= '0;
			FB_RD <= 0;
			FB_RD_WAIT <= 0;""")
rep("""				if (!RD_N && !FIFO_FB_WRITE && FIFO_EMPTY) begin
					FB_RD <= 1;
					ACCESS_WAIT <= ACCESS_WAIT - 3'd1;
					if (!ACCESS_WAIT) begin
						DO <= FB_DRAW_Q;
						FB_RD <= 0;
						ACK_N <= 0;
					end
				end else if ((!LWR_N || !UWR_N) && !FIFO_FULL) begin""",
"""				if (!RD_N && !FIFO_FB_WRITE && FIFO_EMPTY) begin
					// read through the DDR3 draw port: one request, acknowledged when the data is back
					// (the real DRAM answered in ~7 clocks; DDR3 takes a little longer on a cache miss)
					if (!FB_RD && !FB_RD_WAIT) begin
						FB_RD <= 1;
						FB_RD_WAIT <= 1;
					end else begin
						FB_RD <= 0;
						if (FBD_RDY) begin
							DO <= FBD_DI;
							FB_RD_WAIT <= 0;
							ACK_N <= 0;
						end
					end
				end else if ((!LWR_N || !UWR_N) && !FIFO_FULL) begin""")
rep("""			end else if (LWR_N && UWR_N && RD_N && !ACK_N) begin
				ACK_N <= 1;
				ACCESS_WAIT <= 3'd6;
			end

			if (FILL_PEND && CE_R) begin
				FILL_PEND <= 0;
				FILL_EXEC <= 1;
			end else if (FILL_EXEC && CE_R) begin""",
"""			end else if (LWR_N && UWR_N && RD_N && !ACK_N) begin
				ACK_N <= 1;
			end

			if (FILL_PEND && CE_R) begin
				FILL_PEND <= 0;
				FILL_EXEC <= 1;
			end else if (FILL_EXEC && CE_R && !FBD_BUSY) begin	// auto-fill writes queue in the DDR3 FIFO: pause while it is full""")
rep("		bit  [2:0] ACCESS_WAIT;\n", "")

# FIFO drain waits for room in the DDR3 write FIFO
rep("			if (!FIFO_EMPTY && !FIFO_FB_WRITE) begin\n\t\t\t\t{FIFO_FB_A,FIFO_FB_WE,FIFO_FB_D} <= FIFO_Q;",
    "			if (!FIFO_EMPTY && !FIFO_FB_WRITE && !FBD_BUSY) begin\n\t\t\t\t{FIFO_FB_A,FIFO_FB_WE,FIFO_FB_D} <= FIFO_Q;")

# display stream from the prefetched line buffer
rep("""				if (H_CNT == 9'h017-1) begin
					LINE_LEAD <= {FB_DISP_Q, SFT | &MODE};
					PIX_DATA <= '0;
				end""", """				if (H_CNT == 9'h017-1) begin
					LINE_LEAD <= {LP_START, SFT | &MODE};	// the line-table entry, prefetched during HBLANK
					PIX_DATA <= '0;
				end""")
rep("""						2'b01: begin
							LINE_LEAD <= LINE_LEAD + 17'd1;
							PIX_DATA <= FB_DISP_Q;
						end
						2'b10:  begin
							PIX_DATA <= FB_DISP_Q;
							LINE_LEAD <= LINE_LEAD + 17'd2;
						end
						2'b11: begin
							PIX_DATA[15:8] <= PIX_DATA[15:8] - 8'd1;
							if (PIX_DATA[15:8] == 8'd0) begin
								PIX_DATA <= FB_DISP_Q;
								LINE_LEAD <= LINE_LEAD + 17'd2;
							end
						end""", """						2'b01: begin
							LINE_LEAD <= LINE_LEAD + 17'd1;
							PIX_DATA <= LB_Q;
						end
						2'b10:  begin
							PIX_DATA <= LB_Q;
							LINE_LEAD <= LINE_LEAD + 17'd2;
						end
						2'b11: begin
							PIX_DATA[15:8] <= PIX_DATA[15:8] - 8'd1;
							if (PIX_DATA[15:8] == 8'd0) begin
								PIX_DATA <= LB_Q;
								LINE_LEAD <= LINE_LEAD + 17'd2;
							end
						end""")
rep("""	always_comb begin
		if (H_CNT == 9'h017-1)
			FB_DISP_A = {8'h00,V_CNT[7:0]};
		else
			FB_DISP_A = LINE_LEAD[16:1];
	end
""", """	// line buffer index = word address - the beat-aligned start of the prefetched line
	wire [15:0] LB_OFFS = LINE_LEAD[16:1] - LP_BASE;
	assign LB_ADDR = LB_OFFS[8:0];

	// prefetch the coming line a few dots after HSYNC: V_CNT already holds its number (it steps at
	// H_CNT 0x149) and VBLANK has ended for line 0 (at 0x1CD), so FS is final for the frame
	assign LP_REQ  = DOT_CE && H_CNT == 9'h1D0;
	assign LP_FB   = FS;
	assign LP_LINE = V_CNT[7:0];
""")

rep("""	always @(posedge CLK) FB_DISP_RD <= DOT_CE | USE_ASYNC_FB;

	assign FB_DRAW_A  = FILL_EXEC ? AFAR : FB_WR ? FIFO_FB_A[16:1] : A[16:1];
	assign FB_DRAW_D  = FILL_EXEC ? AFDR : FB_WR ? FIFO_FB_D       : DI;
	assign FB_DRAW_WE = FILL_EXEC ? {2{FILL_EXEC & (~|FILL_WAIT | USE_ASYNC_FB)}} : {FB_WR & FIFO_FB_WE[1] & ((|FIFO_FB_D[15:8] & FIFO_FB_A[17]) | ((|FIFO_FB_D[15:8] | FIFO_FB_WE[0]) & ~FIFO_FB_A[17])),
	                                                                                 FB_WR & FIFO_FB_WE[0] & ((|FIFO_FB_D[ 7:0] & FIFO_FB_A[17]) | ((|FIFO_FB_D[ 7:0] | FIFO_FB_WE[1]) & ~FIFO_FB_A[17]))};
	assign FB_DRAW_RD = FILL_EXEC ? 1'b0 : FB_RD;

	assign FB_DRAW_Q = FS ? FB0_DI : FB1_DI;
	assign FB_DISP_Q = FS ? FB1_DI : FB0_DI;

	assign FB0_A  = FS ? FB_DRAW_A : FB_DISP_A;
	assign FB0_DO = FB_DRAW_D;
	assign FB0_WE = FS ? FB_DRAW_WE : 2'b00;
	assign FB0_RD = FS ? FB_DRAW_RD : FB_DISP_RD;

	assign FB1_A  = FS ? FB_DISP_A : FB_DRAW_A;
	assign FB1_DO = FB_DRAW_D;
	assign FB1_WE = FS ? 2'b00      : FB_DRAW_WE;
	assign FB1_RD = FS ? FB_DISP_RD : FB_DRAW_RD;
""", """	assign FB_DRAW_A  = FILL_EXEC ? AFAR : FB_WR ? FIFO_FB_A[16:1] : A[16:1];
	assign FB_DRAW_D  = FILL_EXEC ? AFDR : FB_WR ? FIFO_FB_D       : DI;
	assign FB_DRAW_WE = FILL_EXEC ? {2{FILL_EXEC & ~|FILL_WAIT}} : {FB_WR & FIFO_FB_WE[1] & ((|FIFO_FB_D[15:8] & FIFO_FB_A[17]) | ((|FIFO_FB_D[15:8] | FIFO_FB_WE[0]) & ~FIFO_FB_A[17])),
	                                                                FB_WR & FIFO_FB_WE[0] & ((|FIFO_FB_D[ 7:0] & FIFO_FB_A[17]) | ((|FIFO_FB_D[ 7:0] | FIFO_FB_WE[1]) & ~FIFO_FB_A[17]))};
	assign FB_DRAW_RD = FILL_EXEC ? 1'b0 : FB_RD;

	// the drawn buffer is the one not displayed: FS=1 displays buffer 1 and draws buffer 0
	assign FBD_FB = ~FS;
	assign FBD_A  = FB_DRAW_A;
	assign FBD_DO = FB_DRAW_D;
	assign FBD_WE = FB_DRAW_WE;
	assign FBD_RD = FB_DRAW_RD;
""")

open(p, "w", encoding="utf-8").write(s)
print("vdp ok")
