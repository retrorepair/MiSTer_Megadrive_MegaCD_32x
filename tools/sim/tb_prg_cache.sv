`timescale 1ns/1ps
//============================================================================
//  Self-checking testbench for core/rtl/prg_cache.sv.
//
//  Two builds were burned guessing at this handshake. This models the two
//  things the cache actually sits between, faithfully enough to be worth
//  trusting:
//
//   * sdram_port_model - sdram.sv's port 2 as it really behaves: a request is
//     captured on the RISING edge of rd/wr and only while the controller is
//     idle; the pending flag is dropped if the strobe goes away before then
//     (`old_rd <= old_rd & rd`); busy is ram_req|ram_req_d|ram_req_d2, so it
//     stays high two cycles after the data register loads; dout_p loads one
//     cycle after the internal capture. An injectable delay models another
//     port holding the controller.
//
//   * asic_model - ASIC.vhd's PRSS, on clk_sys = clk_ram/2:
//     PRS_IDLE issues only when PRG_RDY='1', PRS_WAIT waits for PRG_RDY='0'
//     (meaning ACCEPTED), PRS_READ latches PRG_DI when PRG_RDY='1' again, and
//     PRS_WRITE drops the write strobes as soon as PRS_WAIT has seen busy go
//     high - it does NOT wait for the transfer to finish.
//
//  The driver issues a random stream of reads and writes against a reference
//  memory and fails on the first read that does not return what was last
//  written there.
//============================================================================

module sdram_port_model #(parameter DELAYMAX = 12)
(
	input             clk,
	input      [24:1] addr,
	input      [15:0] din,
	output     [15:0] dout,
	input             rd,
	input             wrl,
	input             wrh,
	output            busy,
	input      [31:0] seed
);
	reg [15:0] mem[0:16383];          // indexed by addr[14:1]
	reg        req = 0, req_d = 0, req_d2 = 0;
	reg        old_rd = 0, old_wr = 0;
	reg  [3:0] cnt;
	reg [15:0] cap, dout_p;
	reg [24:1] a_l;
	reg [15:0] d_l;
	reg  [1:0] be_l;
	reg        we_l;
	reg [31:0] lfsr;
	reg  [4:0] hold = 0;              // another port owning the controller

	wire wr = wrl | wrh;
	assign busy = req | req_d | req_d2;
	assign dout = dout_p;

	initial lfsr = seed;

	always @(posedge clk) begin
		old_rd <= old_rd & rd;        // exactly sdram.sv: a strobe withdrawn early loses the request
		old_wr <= old_wr & wr;
		req_d  <= req;
		req_d2 <= req_d;
		lfsr   <= {lfsr[30:0], lfsr[31] ^ lfsr[21] ^ lfsr[1] ^ lfsr[0]};

		if (hold) hold <= hold - 1'd1;

		if (!req) begin
			if (!hold && ((rd && !old_rd) || (wr && !old_wr))) begin
				old_rd <= rd;
				old_wr <= wr;
				a_l  <= addr;
				d_l  <= din;
				be_l <= {wrh, wrl};
				we_l <= wr;
				req  <= 1;
				cnt  <= 4'd6;
			end
			else if (!hold && (rd || wr) && (lfsr[3:0] == 0)) begin
				hold <= lfsr[8:4] & 5'h0F;   // let another port in now and then
			end
		end
		else begin
			cnt <= cnt - 1'd1;
			if (cnt == 0) begin
				if (we_l) begin
					if (be_l[0]) mem[a_l[14:1]][7:0]  <= d_l[7:0];
					if (be_l[1]) mem[a_l[14:1]][15:8] <= d_l[15:8];
				end
				else cap <= mem[a_l[14:1]];
				req <= 0;
			end
		end

		if (req && cnt == 0 && !we_l) dout_p <= mem[a_l[14:1]];
	end
endmodule


module tb_prg_cache;

	reg clk = 0;                       // clk_ram
	reg reset = 1;
	always #5 clk = ~clk;              // 100 MHz-ish, stands in for clk_ram

	reg clk_sys = 0;                   // clk_ram / 2, as in the core
	always @(posedge clk) clk_sys <= ~clk_sys;

	reg en = 1, nohit = 0;
	integer hits = 0, misses = 0;
	always @(posedge clk)
		if (dut.state == 3'd2) begin           // S_LOOK: the cycle the decision is made
			if (dut.hit && !nohit) hits = hits + 1; else misses = misses + 1;
		end

	// --- Mega CD side, driven by the ASIC model
	reg  [24:1] a;
	reg  [15:0] din;
	wire [15:0] dout;
	reg         rd = 0, wrl = 0, wrh = 0;
	wire        busy;

	// --- SDRAM side
	wire [24:1] s_a;
	wire [15:0] s_din, s_dout;
	wire        s_rd, s_wrl, s_wrh, s_busy;

	prg_cache #(.IDX(9)) dut
	(
		.clk(clk), .reset(reset), .en(en), .nohit(nohit),
		.a(a), .din(din), .dout(dout), .rd(rd), .wrl(wrl), .wrh(wrh), .busy(busy),
		.s_a(s_a), .s_din(s_din), .s_dout(s_dout),
		.s_rd(s_rd), .s_wrl(s_wrl), .s_wrh(s_wrh), .s_busy(s_busy)
	);

	sdram_port_model sdr
	(
		.clk(clk), .addr(s_a), .din(s_din), .dout(s_dout),
		.rd(s_rd), .wrl(s_wrl), .wrh(s_wrh), .busy(s_busy), .seed(32'h1234_5678)
	);

	// ---- ASIC.vhd PRSS, on clk_sys
	localparam P_IDLE = 0, P_WAIT = 1, P_READ = 2, P_WRITE = 3, P_END = 4;
	reg  [2:0] prss = P_IDLE;
	reg        dtack_n = 1;
	reg [15:0] captured;
	wire       rdy = ~busy;

	reg         want = 0;              // the driver asks for an access
	reg  [24:1] want_a;
	reg [15:0]  want_d;
	reg  [1:0]  want_be;
	reg         want_rnw;
	reg         done = 0;

	reg [15:0] ref_mem[0:16383];
	integer    errors = 0, reads = 0, writes = 0, i;
	reg [31:0] rnd;

	always @(posedge clk_sys) begin
		done <= 0;
		case (prss)
			P_IDLE: if (want && dtack_n && rdy) begin
				a   <= want_a;
				din <= want_d;
				wrl <= want_rnw ? 1'b0 : want_be[0];
				wrh <= want_rnw ? 1'b0 : want_be[1];
				rd  <= want_rnw;
				prss <= P_WAIT;
			end
			P_WAIT: if (!rdy) prss <= rd ? P_READ : P_WRITE;
			P_READ: if (rdy) begin
				rd <= 0;
				captured <= dout;
				dtack_n <= 0;
				prss <= P_END;
			end
			P_WRITE: begin                     // drops the strobes the moment busy went high
				wrl <= 0; wrh <= 0;
				dtack_n <= 0;
				prss <= P_END;
			end
			P_END: begin
				dtack_n <= 1;
				done <= 1;
				prss <= P_IDLE;
			end
		endcase
	end

	task do_access(input rnw, input [24:1] addr, input [15:0] data, input [1:0] be);
		begin
			want_a = addr; want_d = data; want_be = be; want_rnw = rnw; want = 1;
			@(posedge done);
			want = 0;
			@(posedge clk_sys);
			if (rnw) begin
				reads = reads + 1;
				if (captured !== ref_mem[addr[14:1]]) begin
					errors = errors + 1;
					$display("  MISMATCH read  a=%06X got=%04X want=%04X   (read %0d)",
					         addr, captured, ref_mem[addr[14:1]], reads);
					if (errors > 8) begin $display("too many, stopping"); $finish; end
				end
			end
			else begin
				writes = writes + 1;
				if (be[0]) ref_mem[addr[14:1]][7:0]  = data[7:0];
				if (be[1]) ref_mem[addr[14:1]][15:8] = data[15:8];
			end
		end
	endtask

	initial begin
		if (!$value$plusargs("EN=%d", i))    i = 1;
		en = i[0];
		if (!$value$plusargs("NOHIT=%d", i)) i = 0;
		nohit = i[0];
		$display("### en=%0d nohit=%0d", en, nohit);
		for (i = 0; i < 16384; i = i + 1) begin
			ref_mem[i] = 16'h0000;
			sdr.mem[i] = 16'h0000;
		end
		repeat (4) @(posedge clk);
		reset = 0;
		repeat (600) @(posedge clk);        // let the cache clear its valid bits

		$display("--- phase 1: seed memory with known words ---");
		for (i = 0; i < 64; i = i + 1)
			do_access(0, {10'd0, 14'(i)}, 16'hA000 + i[15:0], 2'b11);

		$display("--- phase 2: random read/write mix over a small working set ---");
		rnd = 32'hC0FFEE01;
		for (i = 0; i < 3000; i = i + 1) begin
			rnd = {rnd[30:0], rnd[31] ^ rnd[21] ^ rnd[1] ^ rnd[0]};
			if (rnd[15:14] == 2'b00)
				do_access(0, {10'd0, 14'(rnd[9:4] & 6'h3F)}, rnd[31:16],
				          (rnd[13:12] == 2'b00) ? 2'b01 : (rnd[13:12] == 2'b01) ? 2'b10 : 2'b11);
			else
				do_access(1, {10'd0, 14'(rnd[9:4] & 6'h3F)}, 16'h0000, 2'b11);
		end

		$display("--- phase 3: read-after-write to the same word, back to back ---");
		for (i = 0; i < 200; i = i + 1) begin
			do_access(0, {10'd0, 14'd7}, 16'h1000 + i[15:0], 2'b11);
			do_access(1, {10'd0, 14'd7}, 16'h0000, 2'b11);
		end

		$display("--- phase 4: addresses that collide on the same cache index ---");
		for (i = 0; i < 400; i = i + 1) begin
			do_access(0, {10'd0, 14'd5},      16'h2000 + i[15:0], 2'b11);
			do_access(0, {10'd1, 14'd5},      16'h3000 + i[15:0], 2'b11);
			do_access(1, {10'd0, 14'd5},      16'h0000, 2'b11);
			do_access(1, {10'd1, 14'd5},      16'h0000, 2'b11);
		end

		$display("=== %0d reads, %0d writes, %0d cache hits, %0d misses, %0d MISMATCHES ===",
		         reads, writes, hits, misses, errors);
		if (errors == 0) $display("PASS");
		else             $display("FAIL");
		$finish;
	end

	initial begin
		#20000000;
		$display("TIMEOUT - the handshake deadlocked (prss=%0d busy=%b rd=%b wrl=%b s_rd=%b s_busy=%b state=%0d)",
		         prss, busy, rd, wrl, s_rd, s_busy, dut.state);
		$finish;
	end

endmodule
