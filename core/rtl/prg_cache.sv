//============================================================================
//  Mega CD PRG-RAM read cache on SDRAM port 2  (tools/phase54_prg_cache.py)
//
//  WHY
//  The four remaining mcd-verificator failures - VAR TESTS 02, IRQ TEST 09,
//  REG 8030 07 and CDC FLAGS 40 - are one cause, and it is not fpgagen's 68000.
//  The main CPU fetches its instructions from cartridge ROM on the same SDRAM
//  controller the Mega CD sub-CPU reads PRG-RAM from, so its bus cycles are
//  stretched by contention. Measured:
//
//      sub-CPU PRG-RAM  2.13M reads/s x 7 clk_ram (65 ns) = 13.7% occupancy
//      collision cost on a 521 ns 68000 bus cycle         ~1.7%
//      refresh, 7 clk_ram every 766                       ~0.9%
//                                                  total  ~2.6%
//
//  against the 2.59% the CDC FLAGS poll loop is short of. Ruled out with
//  arithmetic or on hardware first: the sub-CPU clock (exactly 12,500,000.000
//  Hz), the main clock (exactly 53,693,175/7), the prg_first port priority
//  (A/B'd live through MegaCD.CFG bit 24 - no effect on any of the four) and
//  SH-2 contention (both PCs read 0 for a non-32X cartridge).
//
//  The sub-CPU is not streaming. Measured with scratch/subhist.py during a
//  running CD game, its address bus showed 62 distinct words in 8000 samples
//  and 41 in 4000: it re-fetches tight loops, which is also exactly what the
//  verificator's poll loop does. TEMPORAL locality alone therefore removes
//  almost all of that 13.7%. Spatial locality would not help at all - sdram.sv
//  moves one word per 7-cycle access with no burst support (sdram.sv:107-112),
//  so a line fill costs one controller slot per word and saves nothing. Hence
//  one word per entry, direct mapped, no line.
//
//  WHAT THIS DELIBERATELY DOES NOT CHANGE
//  A hit is held busy for as long as an uncontended miss takes, so the Mega CD
//  sees the access latency it sees today. What disappears is the SDRAM slot,
//  which is the entire point: the goal is to stop the sub-CPU stealing cycles
//  from the MD's cartridge fetches, not to make the sub-CPU faster than the
//  hardware it models.
//
//  COHERENCY - why a cache here is safe when one inside the Mega CD would not be
//  PRG-RAM has three writers: the sub-CPU, the MD through the gate-array window
//  at $420000 in mode 1, and CDC DMA. All three are arbitrated onto this ONE
//  port inside ASIC.vhd - PRG_RAM_ADDR/DO/WRL/WRH/RD are driven from S68K_*,
//  EXT_* and DMA_* in the same process (ASIC.vhd:1471, 1555, 1574) - so every
//  write passes through here and updates the cache. No other SDRAM port
//  addresses this region either: port 0 is the cartridge (0000000-0EFFFFF),
//  port 1 the BIOS (0F00000-0F1FFFF), port 3 PCM wave RAM (1080000-108FFFF)
//  and port 4 the HPS load/save path (ROM, BIOS and cartridge RAM only).
//
//  Writes are write-through and always reach the SDRAM; only reads are served
//  from the cache.
//============================================================================

module prg_cache #(parameter IDX = 9)   // 2**IDX entries, direct mapped, one 16-bit word each
(
	input             clk,          // clk_ram, the SDRAM controller's clock
	input             reset,

	// Mega CD side: ASIC.vhd's PRG_* port, same protocol sdram.sv presents
	input      [24:1] a,
	input      [15:0] din,
	output     [15:0] dout,
	input             rd,           // level, captured on its rising edge
	input             wrl,
	input             wrh,
	output            busy,         // rises after the request, falls when the data is valid

	// SDRAM port 2
	output     [24:1] s_a,
	output     [15:0] s_din,
	input      [15:0] s_dout,
	output reg        s_rd,
	output            s_wrl,
	output            s_wrh,
	input             s_busy
);

localparam TAGW = 25 - 1 - IDX;          // a is [24:1]: IDX index bits, the rest is tag
localparam W    = 1 + TAGW + 16;         // {valid, tag, data}

// The address and the write strobes go straight through. sdram.sv latches both when it accepts a
// request, and only the READ strobe is ever withheld - a hit must not raise it, or the slot this
// whole module exists to save is spent anyway.
assign s_a   = a;
assign s_din = din;
assign s_wrl = wrl;
assign s_wrh = wrh;

wire            wr  = wrl | wrh;
wire [IDX-1:0]  idx = a[IDX:1];
wire [TAGW-1:0] tag = a[24:IDX+1];

// Tag/data store. Held in MLABs rather than M10K on purpose: block RAM is this design's binding
// resource at 539 of 553 blocks, while ALMs sit at 79%.
(* ramstyle = "MLAB, no_rw_check" *) reg [W-1:0] mem[2**IDX];
reg  [W-1:0] q;
reg  [W-1:0] wd;
reg [IDX-1:0] wa;
reg          we;

always @(posedge clk) begin
	if (we) mem[wa] <= wd;
	q <= mem[idx];                       // one cycle of latency: valid in S_LOOK
end

wire hit = q[W-1] && q[W-2 -: TAGW] == tag;

localparam S_INIT = 3'd0,   // clear every valid bit: MLABs come up undefined
           S_IDLE = 3'd1,
           S_LOOK = 3'd2,   // q is valid this cycle
           S_HIT  = 3'd3,
           S_MISS = 3'd4,
           S_WR   = 3'd5;

reg  [2:0] state = S_INIT;
reg  [IDX:0] icnt = 0;
reg  [3:0] hcnt;
reg        saw_busy;
reg        old_rd, old_wr;
reg [TAGW-1:0] q_tag;
reg [IDX-1:0]  q_idx;
reg [15:0] dout_r;

// The write data and byte enables MUST be latched with the request. ASIC.vhd's PRS_WAIT drops
// PRG_RAM_WRL/WRH as soon as it sees busy go HIGH (PRS_WRITE, ASIC.vhd:1632) - it does not wait for
// busy to fall - so by the time the SDRAM has finished the write, wrl/wrh/din have already gone.
// Merging from the live pins would store the OLD word back and mark it valid, which is exactly the
// kind of silent staleness that corrupts sub-CPU code.
reg [15:0] q_din;
reg        q_wrl, q_wrh;

assign dout = dout_r;
assign busy = (state != S_IDLE);         // high through S_INIT too, so no request is taken early

always @(posedge clk) begin
	old_rd <= rd;
	old_wr <= wr;
	we     <= 0;

	if (reset) begin
		state    <= S_INIT;
		icnt     <= 0;
		s_rd     <= 0;
		saw_busy <= 0;
		old_rd   <= 0;
		old_wr   <= 0;
	end
	else case (state)
		S_INIT: begin
			we   <= 1;
			wa   <= icnt[IDX-1:0];
			wd   <= '0;
			icnt <= icnt + 1'd1;
			if (icnt == {1'b0,{IDX{1'b1}}}) state <= S_IDLE;
		end

		S_IDLE: begin
			saw_busy <= 0;
			// Edge-triggered exactly as sdram.sv is, so a strobe left high after one access
			// cannot be mistaken for the next.
			if (rd && !old_rd) begin
				q_idx <= idx; q_tag <= tag;
				state <= S_LOOK;
			end
			else if (wr && !old_wr) begin
				q_idx <= idx; q_tag <= tag;
				q_din <= din; q_wrl <= wrl; q_wrh <= wrh;
				state <= S_WR;
			end
		end

		S_LOOK: begin
			if (hit) begin
				dout_r <= q[15:0];
				hcnt   <= 4'd8;          // S_LOOK + 9 = 10 clk_ram cycles, >= an uncontended miss
				state  <= S_HIT;
			end
			else begin
				s_rd  <= 1;
				state <= S_MISS;
			end
		end

		S_HIT: begin
			hcnt <= hcnt - 1'd1;
			if (!hcnt) state <= S_IDLE;
		end

		S_MISS: begin
			if (s_busy) saw_busy <= 1;
			if (saw_busy && !s_busy) begin   // busy rose and fell: the word is back
				dout_r <= s_dout;
				wa <= q_idx;
				wd <= {1'b1, q_tag, s_dout};
				we <= 1;
				s_rd  <= 0;
				state <= S_IDLE;
			end
		end

		S_WR: begin
			if (s_busy) saw_busy <= 1;
			if (saw_busy && !s_busy) begin
				wa <= q_idx;
				if (hit) begin
					// merge, so a byte write cannot leave half a stale word behind
					wd <= {1'b1, q_tag, q_wrh ? q_din[15:8] : q[15:8], q_wrl ? q_din[7:0] : q[7:0]};
					we <= 1;
				end
				else if (q_wrl && q_wrh) begin
					wd <= {1'b1, q_tag, q_din};   // full word: allocate
					we <= 1;
				end
				// a byte write that misses allocates nothing: half a word is not a cache line
				state <= S_IDLE;
			end
		end

		default: state <= S_IDLE;
	endcase
end

endmodule
