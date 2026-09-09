//============================================================================
//  RF5C164 (Mega CD PCM) sample RAM in SDRAM
//
//  The FPGA does not have enough M10K blocks for the whole Mega CD plus the
//  NukedMD chipset, so the 64KB PCM wave RAM lives in SDRAM. Every master of
//  this memory tolerates latency:
//   * sub CPU / gate array DMA writes go through a small FIFO (the sub CPU is
//     held with /DTACK when the FIFO is full),
//   * sub CPU reads hold /DTACK until the data has arrived,
//   * the sample fetcher gets one read per channel slot (~1.9us at 53.69MHz),
//     and the fetch is issued as soon as the channel address changes.
//  Ordering: fetches first (deadline), then queued writes, then CPU reads.
//
//  Copyright (c) 2026
//  This program is free software; you can redistribute it and/or modify it
//  under the terms of the GNU General Public License as published by the Free
//  Software Foundation; either version 2 of the License, or (at your option)
//  any later version.
//============================================================================

module pcm_mem
(
	input             clk,        // Mega CD clock (53.69 MHz)
	input             reset,

	// RF5C164 side
	input      [15:0] cpu_addr,
	input       [7:0] cpu_din,
	input             cpu_wr,     // level, one access per rising edge
	input             cpu_rd,     // level, one access per rising edge
	output      [7:0] cpu_dout,   // held until the next read
	output            cpu_rdy,    // 0: hold /DTACK (read outstanding or FIFO full)

	input      [15:0] smp_addr,
	output reg  [7:0] smp_dout,
	output reg        late,       // telemetry: the chip moved to a new sample before the previous fetch returned

	// SDRAM port (busy-style, request is a level)
	output reg [15:0] mem_addr,
	output reg  [7:0] mem_din,
	output reg        mem_rd,
	output reg        mem_wr,
	input      [15:0] mem_dout,
	input             mem_busy
);

// write FIFO
(* ramstyle = "logic" *) reg [23:0] fifo[8];
reg  [2:0] wr_ptr, rd_ptr;
wire       fifo_empty = (wr_ptr == rd_ptr);
wire       fifo_full  = (wr_ptr[2:0] == rd_ptr[2:0] + 3'd7);

reg        rd_pend;
reg [15:0] rd_addr;
reg  [7:0] rd_data;

reg        smp_req;
reg [15:0] smp_addr_q;

reg        old_wr, old_rd, old_busy;

assign cpu_dout = rd_data;
assign cpu_rdy  = ~(cpu_rd & ~old_rd) & ~rd_pend & ~fifo_full;

localparam IDLE = 0, REQ = 1, WAIT = 2;
reg [1:0] state;
reg [1:0] kind; // 0: fetch, 1: write, 2: cpu read

always @(posedge clk) begin
	old_wr   <= cpu_wr;
	old_rd   <= cpu_rd;
	old_busy <= mem_busy;

	if(reset) begin
		wr_ptr <= 0; rd_ptr <= 0;
		rd_pend <= 0;
		smp_req <= 1;
		smp_addr_q <= 0;
		mem_rd <= 0; mem_wr <= 0;
		state <= IDLE;
	end
	else begin
		// accept requests from the chip
		if(cpu_wr & ~old_wr & ~fifo_full) begin
			fifo[wr_ptr] <= {cpu_addr, cpu_din};
			wr_ptr <= wr_ptr + 1'd1;
		end
		if(cpu_rd & ~old_rd) begin
			rd_pend <= 1;
			rd_addr <= cpu_addr;
		end
		late <= 0;
		if(smp_addr != smp_addr_q) begin
			smp_addr_q <= smp_addr;
			smp_req <= 1;
			if(smp_req) late <= 1;   // previous sample never delivered
		end

		case(state)
			IDLE: begin
				if(smp_req) begin
					mem_addr <= smp_addr_q;
					mem_rd <= 1;
					kind <= 0;
					state <= REQ;
				end
				else if(~fifo_empty) begin
					mem_addr <= fifo[rd_ptr][23:8];
					mem_din  <= fifo[rd_ptr][7:0];
					mem_wr <= 1;
					kind <= 1;
					state <= REQ;
				end
				else if(rd_pend) begin
					mem_addr <= rd_addr;
					mem_rd <= 1;
					kind <= 2;
					state <= REQ;
				end
			end

			REQ: if(mem_busy) state <= WAIT; // accepted by the controller

			WAIT: if(~mem_busy) begin
				mem_rd <= 0;
				mem_wr <= 0;
				case(kind)
					0: begin smp_dout <= mem_dout[7:0]; smp_req <= (smp_addr_q != mem_addr); end
					1: rd_ptr <= rd_ptr + 1'd1;
					2: begin rd_data <= mem_dout[7:0]; rd_pend <= 0; end
				endcase
				state <= IDLE;
			end
		endcase
	end
end

endmodule
