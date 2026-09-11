//
// sdram.v
//
// sdram controller implementation
// Copyright (c) 2018 Sorgelig
//
// This source file is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published
// by the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.
//
// This source file is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.
//
// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.
//
// MegaCD/NukedMD: extended from 3 to 5 ports (fixed priority 0 > 1 > 2 > 3 > 4) so that the
// cartridge, the Mega CD BIOS ROM, the Mega CD PRG-RAM and the load/save path each own
// a port. A request is a level: it is captured on its rising edge and stays pending until
// the controller accepts it, so a request raised while another port is being served is
// never lost.
//

module sdram
(

	// interface to the MT48LC16M16 chip
	inout  reg [15:0] SDRAM_DQ,   // 16 bit bidirectional data bus
	output reg [12:0] SDRAM_A,    // 13 bit multiplexed address bus
	output reg        SDRAM_DQML, // byte mask
	output reg        SDRAM_DQMH, // byte mask
	output reg  [1:0] SDRAM_BA,   // two banks
	output            SDRAM_nCS,  // a single chip select
	output reg        SDRAM_nWE,  // write enable
	output reg        SDRAM_nRAS, // row address select
	output reg        SDRAM_nCAS, // columns address select
	output            SDRAM_CLK,
	output            SDRAM_CKE,

	// cpu/chipset interface
	input             init,			// init signal after FPGA config to initialize RAM
	input             clk,			// sdram is accessed at up to 128MHz

	input      [24:1] addr0,
	input             rd0,
	input             wrl0,
	input             wrh0,
	input      [15:0] din0,
	output     [15:0] dout0,
	output            busy0,

	input      [24:1] addr1,
	input             rd1,
	input             wrl1,
	input             wrh1,
	input      [15:0] din1,
	output     [15:0] dout1,
	output            busy1,

	input      [24:1] addr2,
	input             rd2,
	input             wrl2,
	input             wrh2,
	input      [15:0] din2,
	output     [15:0] dout2,
	output            busy2,

	input      [24:1] addr3,
	input             rd3,
	input             wrl3,
	input             wrh3,
	input      [15:0] din3,
	output     [15:0] dout3,
	output            busy3,

	input      [24:1] addr4,
	input             rd4,
	input             wrl4,
	input             wrh4,
	input      [15:0] din4,
	output     [15:0] dout4,
	output            busy4,

	// Fixed priority is 0 > 1 > 2 > 3 > 4. With prg_first the Mega CD PRG-RAM (port 2) is served
	// ahead of the cartridge (port 0) and the BIOS ROM (port 1): the sub-CPU runs at 12.5 MHz and
	// has 120 ns from /AS to its /DTACK sample, against 195 ns for the 7.67 MHz main CPU, so when
	// one of them has to wait it should be the one with the slack. See tools/phase21_prg_priority.py.
	input             prg_first
);

assign SDRAM_nCS = 0;
assign SDRAM_CKE = 1;
assign {SDRAM_DQMH,SDRAM_DQML} = SDRAM_A[12:11];

localparam RASCAS_DELAY   = 3'd2; // tRCD=20ns -> 2 cycles@85MHz
localparam BURST_LENGTH   = 3'd0; // 0=1, 1=2, 2=4, 3=8, 7=full page
localparam ACCESS_TYPE    = 1'd0; // 0=sequential, 1=interleaved
localparam CAS_LATENCY    = 3'd2; // 2/3 allowed
localparam OP_MODE        = 2'd0; // only 0 (standard operation) allowed
localparam NO_WRITE_BURST = 1'd1; // 0=write burst enabled, 1=only single access write

localparam MODE = { 3'b000, NO_WRITE_BURST, OP_MODE, CAS_LATENCY, ACCESS_TYPE, BURST_LENGTH};

localparam STATE_IDLE  = 3'd0;             // state to check the requests
localparam STATE_START = STATE_IDLE+1'd1;  // state in which a new command is started
localparam STATE_CONT  = STATE_START+RASCAS_DELAY;
localparam STATE_READY = STATE_CONT+CAS_LATENCY+1'd1;
localparam STATE_LAST  = STATE_READY;      // last state in cycle

reg  [2:0] state = 0;
reg [22:1] a;
reg [15:0] data;
reg        we;
reg  [1:0] ba = 0;
reg  [1:0] dqm;
reg        active = 0;
reg  [4:0] ram_req = 0;
// Busy is held two extra clk_ram cycles after the data is captured. The consumers run on clk_sys (half
// this clock) and sample a port's data on the SAME edge at which they first see that port's busy drop -
// the 32X's IF takes CDI_SYNC and ROM_WAIT_SYNC on one negedge, the MD and Mega CD do the equivalent.
// That left the combinational path from this register, through the cartridge and 32X muxes, about one
// clk_ram period to settle; the fitter reported it at -8 ns and whether it worked came down to
// placement, corrupting ROM fetches for the 68000, the SH-2s and the Mega CD sub-CPU. Two extra cycles
// give the data ~19 ns before anything samples it (see the matching multicycle in MegaCD.sdc).
reg  [4:0] ram_req_d = 0;
reg  [4:0] ram_req_d2 = 0;

wire [4:0] wr = {wrl4|wrh4,wrl3|wrh3,wrl2|wrh2,wrl1|wrh1,wrl0|wrh0};
wire [4:0] rd = {rd4,rd3,rd2,rd1,rd0};

// `dout` stays exactly as it was: ONE register with ONE load on SDRAM_DQ. That input path is
// tight and fanning it out to five enabled registers kills the capture outright (built as r28:
// both SH-2s dead, no $A151xx traffic). The per-port split below happens a cycle later instead.
reg [15:0] dout;

// One register PER PORT (tools/phase42_sdram_per_port_dout.py). Sharing `dout` across all five let
// any port's read overwrite another's data before its consumer sampled it, corrupting 68000 and
// SH-2 instruction fetches whenever the Mega CD was active.
reg [15:0] dout_p0, dout_p1, dout_p2, dout_p3, dout_p4;
reg  [4:0] dout_sel;

assign dout0 = dout_p0;
assign dout1 = dout_p1;
assign dout2 = dout_p2;
assign dout3 = dout_p3;
assign dout4 = dout_p4;

localparam [9:0] RFS_CNT = 766;

// access manager
always @(posedge clk) begin
	reg [9:0] rfs_timer = 0;
	reg [4:0] old_rd, old_wr;

	old_rd <= old_rd & rd;
	old_wr <= old_wr & wr;

	if(rfs_timer) rfs_timer <= rfs_timer - 1'd1;

	if(state == STATE_IDLE && mode == MODE_NORMAL) begin
		if (!rfs_timer) begin
			rfs_timer <= RFS_CNT;
			active <= 0;
			we <= 0;
			dqm <= 0;
			state <= STATE_START;
		end
		// Step over the cartridge port when the Mega CD PRG-RAM has a request waiting and
		// prg_first is set - that is all it takes to reorder a fixed-priority else-if chain.
		else if (((~old_rd[0] && rd[0]) || (~old_wr[0] && wr[0]))
		         && !(prg_first && ((~old_rd[2] && rd[2]) || (~old_wr[2] && wr[2])))) begin
			old_rd[0] <= rd[0];
			old_wr[0] <= wr[0];
			{ba, a} <= addr0;
			data <= din0;
			we <= wr[0];
			dqm <= wr[0] ? ~{wrh0,wrl0} : 2'b00;
			active <= 1;
			state <= STATE_START;
			ram_req[0] <= 1;
		end
		else if (((~old_rd[1] && rd[1]) || (~old_wr[1] && wr[1]))
		         && !(prg_first && ((~old_rd[2] && rd[2]) || (~old_wr[2] && wr[2])))) begin
			old_rd[1] <= rd[1];
			old_wr[1] <= wr[1];
			{ba, a} <= addr1;
			data <= din1;
			we <= wr[1];
			dqm <= wr[1] ? ~{wrh1,wrl1} : 2'b00;
			active <= 1;
			state <= STATE_START;
			ram_req[1] <= 1;
		end
		else if ((~old_rd[2] && rd[2]) || (~old_wr[2] && wr[2])) begin
			old_rd[2] <= rd[2];
			old_wr[2] <= wr[2];
			{ba, a} <= addr2;
			data <= din2;
			we <= wr[2];
			dqm <= wr[2] ? ~{wrh2,wrl2} : 2'b00;
			active <= 1;
			state <= STATE_START;
			ram_req[2] <= 1;
		end
		else if ((~old_rd[3] && rd[3]) || (~old_wr[3] && wr[3])) begin
			old_rd[3] <= rd[3];
			old_wr[3] <= wr[3];
			{ba, a} <= addr3;
			data <= din3;
			we <= wr[3];
			dqm <= wr[3] ? ~{wrh3,wrl3} : 2'b00;
			active <= 1;
			state <= STATE_START;
			ram_req[3] <= 1;
		end
		else if ((~old_rd[4] && rd[4]) || (~old_wr[4] && wr[4])) begin
			old_rd[4] <= rd[4];
			old_wr[4] <= wr[4];
			{ba, a} <= addr4;
			data <= din4;
			we <= wr[4];
			dqm <= wr[4] ? ~{wrh4,wrl4} : 2'b00;
			active <= 1;
			state <= STATE_START;
			ram_req[4] <= 1;
		end
	end

	ram_req_d  <= ram_req;
	ram_req_d2 <= ram_req_d;

	if(state == STATE_READY && ram_req) begin
		dout <= SDRAM_DQ;
		active <= 0;
		ram_req <= 0;
	end

	// Hand the captured word to the port that asked for it, one cycle after the capture. ram_req is
	// one-hot for the port being served, and busy (ram_req | ram_req_d | ram_req_d2) stays high for
	// three cycles after STATE_READY, so this lands two cycles before any consumer samples.
	dout_sel <= (state == STATE_READY) ? ram_req : 5'd0;
	if (dout_sel[0]) dout_p0 <= dout;
	if (dout_sel[1]) dout_p1 <= dout;
	if (dout_sel[2]) dout_p2 <= dout;
	if (dout_sel[3]) dout_p3 <= dout;
	if (dout_sel[4]) dout_p4 <= dout;

	if(mode != MODE_NORMAL || state != STATE_IDLE || reset) begin
		state <= state + 1'd1;
		if(state == STATE_LAST) state <= STATE_IDLE;
	end
end

assign busy0 = ram_req[0] | ram_req_d[0] | ram_req_d2[0];
assign busy1 = ram_req[1] | ram_req_d[1] | ram_req_d2[1];
assign busy2 = ram_req[2] | ram_req_d[2] | ram_req_d2[2];
assign busy3 = ram_req[3] | ram_req_d[3] | ram_req_d2[3];
assign busy4 = ram_req[4] | ram_req_d[4] | ram_req_d2[4];


localparam MODE_NORMAL = 2'b00;
localparam MODE_RESET  = 2'b01;
localparam MODE_LDM    = 2'b10;
localparam MODE_PRE    = 2'b11;

// initialization
reg [1:0] mode = 0;
reg [4:0] reset=5'h1f;
always @(posedge clk) begin
	reg init_old=0;
	init_old <= init;

	if(init_old & ~init) reset <= 5'h1f;
	else if(state == STATE_LAST) begin
		if(reset != 0) begin
			reset <= reset - 5'd1;
			if(reset == 14)     mode <= MODE_PRE;
			else if(reset == 3) mode <= MODE_LDM;
			else                mode <= MODE_RESET;
		end
		else mode <= MODE_NORMAL;
	end
end

localparam CMD_NOP             = 3'b111;
localparam CMD_ACTIVE          = 3'b011;
localparam CMD_READ            = 3'b101;
localparam CMD_WRITE           = 3'b100;
localparam CMD_BURST_TERMINATE = 3'b110;
localparam CMD_PRECHARGE       = 3'b010;
localparam CMD_AUTO_REFRESH    = 3'b001;
localparam CMD_LOAD_MODE       = 3'b000;

// SDRAM state machines
always @(posedge clk) begin
	if(state == STATE_START) SDRAM_BA <= (mode == MODE_NORMAL) ? ba : 2'b00;

	SDRAM_DQ <= 'Z;
	casex({active,we,mode,state})
		{2'bXX, MODE_NORMAL, STATE_START}: {SDRAM_nRAS, SDRAM_nCAS, SDRAM_nWE} <= active ? CMD_ACTIVE : CMD_AUTO_REFRESH;
		{2'b11, MODE_NORMAL, STATE_CONT }: {SDRAM_nRAS, SDRAM_nCAS, SDRAM_nWE, SDRAM_DQ} <= {CMD_WRITE, data};
		{2'b10, MODE_NORMAL, STATE_CONT }: {SDRAM_nRAS, SDRAM_nCAS, SDRAM_nWE} <= CMD_READ;

		// init
		{2'bXX,    MODE_LDM, STATE_START}: {SDRAM_nRAS, SDRAM_nCAS, SDRAM_nWE} <= CMD_LOAD_MODE;
		{2'bXX,    MODE_PRE, STATE_START}: {SDRAM_nRAS, SDRAM_nCAS, SDRAM_nWE} <= CMD_PRECHARGE;

		                          default: {SDRAM_nRAS, SDRAM_nCAS, SDRAM_nWE} <= CMD_NOP;
	endcase

	if(mode == MODE_NORMAL) begin
		casex(state)
			STATE_START: SDRAM_A <= a[13:1];
			STATE_CONT:  SDRAM_A <= {dqm, 2'b10, a[22:14]};
		endcase;
	end
	else if(mode == MODE_LDM && state == STATE_START) SDRAM_A <= MODE;
	else if(mode == MODE_PRE && state == STATE_START) SDRAM_A <= 13'b0010000000000;
	else SDRAM_A <= 0;
end

altddio_out
#(
	.extend_oe_disable("OFF"),
	.intended_device_family("Cyclone V"),
	.invert_output("OFF"),
	.lpm_hint("UNUSED"),
	.lpm_type("altddio_out"),
	.oe_reg("UNREGISTERED"),
	.power_up_high("OFF"),
	.width(1)
)
sdramclk_ddr
(
	.datain_h(1'b0),
	.datain_l(1'b1),
	.outclock(clk),
	.dataout(SDRAM_CLK),
	.aclr(1'b0),
	.aset(1'b0),
	.oe(1'b1),
	.outclocken(1'b1),
	.sclr(1'b0),
	.sset(1'b0)
);

endmodule
