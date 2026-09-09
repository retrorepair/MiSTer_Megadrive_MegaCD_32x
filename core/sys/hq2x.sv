//============================================================================
//  Hq2x stand-in: a plain line doubler with the framework Hq2x module's ports.
//
//  The MiSTer framework's scandoubler (sys/scandoubler.v) always instantiates
//  Hq2x and passes every pixel through it, even with the filter disabled. The
//  real filter costs ~660 ALMs and 14 M10K (a 2-line input buffer plus a
//  2-line 2x2 output buffer); this core needs the block RAM for the Mega CD
//  and the 32X, so the "HQ2x" scandoubler option here is a plain doubled
//  picture. The interface contract is that of the original:
//   - ce_in ticks four times per input pixel (cyc 0..3); the pixel is sampled
//     at cyc 1 and belongs at column `offs`, which advances at cyc 3;
//   - the falling edge of reset_line (end of HBLANK, sampled on ce_in) starts a
//     new line: offs = 0 and the write buffer toggles; reset_frame's falling
//     edge at that moment restarts at buffer 0;
//   - the output side reads a doubled line at ce_out: read_x counts output
//     sub-pixels (two per input pixel, read_x[0]), read_y[1] selects the line
//     buffer, read_y[0] the vertical sub-line (identical here), hblank resets.
//============================================================================

module Hq2x #(parameter LENGTH, parameter HALF_DEPTH)
(
	input             clk,

	input             ce_in,
	input  [DWIDTH:0] inputpixel,
	input             mono,
	input             disable_hq2x,
	input             reset_frame,
	input             reset_line,

	input             ce_out,
	input       [1:0] read_y,
	input             hblank,
	output [DWIDTH:0] outpixel
);

localparam AWIDTH = $clog2(LENGTH)-1;
localparam DWIDTH = HALF_DEPTH ? 11 : 23;

reg  [AWIDTH:0] offs;
reg       [1:0] cyc;
reg             curbuf = 0;
reg  [DWIDTH:0] wrpix;
reg             wren;
reg  [AWIDTH:0] wraddr;

// two lines of input pixels; the read side reads the other line, doubled
wire [DWIDTH:0] q;
reg  [AWIDTH+1:0] read_x;
hq2x_buf #(.NUMWORDS(LENGTH*2), .AWIDTH(AWIDTH+1), .DWIDTH(DWIDTH)) linebuf
(
	.clock(clk),
	.data(wrpix),
	.rdaddress({read_x[AWIDTH+1:1], read_y[1]}),
	.wraddress({wraddr, curbuf}),
	.wren(wren),
	.q(q)
);

always @(posedge clk) begin
	reg old_reset_line;
	reg old_reset_frame;

	wren <= 0;
	if(ce_in) begin
		if(~&offs && cyc == 1) begin
			wrpix  <= inputpixel;
			wraddr <= offs;
			wren   <= 1;
		end
		if(cyc == 3 && ~&offs) offs <= offs + 1'd1;

		cyc <= cyc + 1'b1;
		if(old_reset_line && ~reset_line) begin
			old_reset_frame <= reset_frame;
			offs <= 0;
			cyc <= 0;
			curbuf <= ~curbuf;
			if(old_reset_frame & ~reset_frame) curbuf <= 0;
		end
		old_reset_line <= reset_line;
	end
end

reg [DWIDTH:0] outpix;
always @(posedge clk) begin
	if(ce_out) begin
		if(read_x[0]) outpix <= q;
		if(~hblank & ~&read_x) read_x <= read_x + 1'd1;
		if(hblank) read_x <= 0;
	end
end
assign outpixel = outpix;

endmodule

////////////////////////////////////////////////////////////////////////////////////////////////////////

module hq2x_buf #(parameter NUMWORDS, parameter AWIDTH, parameter DWIDTH)
(
	input                 clock,
	input      [DWIDTH:0] data,
	input      [AWIDTH:0] rdaddress,
	input      [AWIDTH:0] wraddress,
	input                 wren,
	output reg [DWIDTH:0] q
);

reg [DWIDTH:0] ram[0:NUMWORDS-1];

always_ff@(posedge clock) begin
	if(wren) ram[wraddress] <= data;
	q <= ram[rdaddress];
end

endmodule
