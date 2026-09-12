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
//  WHAT IT CHANGES FOR THE SUB-CPU
//  A hit answers in ~37 ns instead of the ~93 ns best case of an SDRAM read.
//  That is not the cache running ahead of the hardware it models - it is the
//  opposite. Real PRG-RAM gives the sub-CPU no wait states at all, while this
//  port measured 93 ns at best and 335 ns at worst from /AS to /DTACK against
//  a 120 ns deadline, so the sub-CPU has been losing cycles that the hardware
//  never loses. The verificator reads that deficit two ways: VAR TESTS counts
//  main-CPU polls across a sub-CPU-timed interval and comes out 12-17% high,
//  and IRQ sub-test 6 has the sub-CPU miss INT2 pulses its handler should
//  comfortably keep up with.
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

	// Both settable from the OSD, so this can be bisected on hardware instead of by rebuilding:
	//   en=0            pure pass-through - must behave EXACTLY as the core did before this module
	//   en=1, nohit=1   the wrapper's protocol runs and entries fill, but every read still goes to
	//                   the SDRAM, so a failure here is the handshake, not the cached data
	//   en=1, nohit=0   the cache proper
	input             en,
	input             nohit,

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
	output            s_rd,
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

reg s_rd_r;
assign s_rd = en ? s_rd_r : rd;   // bypass: the read strobe goes straight through

wire            wr  = wrl | wrh;
wire [IDX-1:0]  idx = a[IDX:1];
wire [TAGW-1:0] tag = a[24:IDX+1];

localparam S_INIT = 3'd0,   // clear every valid bit: MLABs come up undefined
           S_IDLE = 3'd1,
           S_LOOK = 3'd2,   // q is valid this cycle
           S_HIT  = 3'd3,
           S_MISS = 3'd4,
           S_WR   = 3'd5,
           S_TAIL = 3'd6;   // write finished: hold busy until we are really idle

reg  [2:0] state = S_INIT;
reg  [IDX:0] icnt = 0;
reg  [3:0] hcnt;
reg        saw_busy;
reg        old_rd, old_wr;
// A request seen while this module is still occupied is REMEMBERED, not dropped. Belt and braces
// against the failure above: nothing else in the chain will ever re-raise a strobe that was ignored.
reg        pend_rd, pend_wr;
reg [TAGW-1:0] q_tag;
reg [IDX-1:0]  q_idx;
reg [15:0] dout_r;

// Tag/data store. Held in MLABs rather than M10K on purpose: block RAM is this design's binding
// resource at 539 of 553 blocks, while ALMs sit at 79%.
(* ramstyle = "MLAB, no_rw_check" *) reg [W-1:0] mem[2**IDX];
reg  [W-1:0] q;
reg  [W-1:0] wd;
reg [IDX-1:0] wa;
reg          we;

// Index with the live address only while idle. ASIC.vhd has TWO state machines writing
// PRG_RAM_ADDR - PRMS for the MD's window and PRSS for the sub-CPU and CDC DMA - and nothing
// guarantees the address holds still for the whole of an access the way it does for sdram.sv, which
// latches it on accept. Freezing the index and comparing against the tag latched with the request
// means a mid-access address change cannot make a different entry answer for this one.
wire [IDX-1:0] ra = (state == S_IDLE) ? idx : q_idx;

always @(posedge clk) begin
	if (we) mem[wa] <= wd;
	q <= mem[ra];                        // one cycle of latency: valid in S_LOOK
end

wire hit = q[W-1] && q[W-2 -: TAGW] == q_tag;


// The write data and byte enables MUST be latched with the request. ASIC.vhd's PRS_WAIT drops
// PRG_RAM_WRL/WRH as soon as it sees busy go HIGH (PRS_WRITE, ASIC.vhd:1632) - it does not wait for
// busy to fall - so by the time the SDRAM has finished the write, wrl/wrh/din have already gone.
// Merging from the live pins would store the OLD word back and mark it valid, which is exactly the
// kind of silent staleness that corrupts sub-CPU code.
reg [15:0] q_din;
reg        q_wrl, q_wrh;

assign dout = en ? dout_r : s_dout;

// busy must NOT rise merely because a request has been noticed. ASIC.vhd's PRS_WAIT takes
// "busy has gone high" to mean "the SDRAM controller has accepted this request", and PRS_WRITE then
// drops PRG_RAM_WRL/WRH immediately. sdram.sv only captures a request on the RISING edge of its
// strobe and clears the pending flag when the strobe goes away (`old_wr <= old_wr & wr`), so a
// strobe withdrawn before the controller is free LOSES THE WRITE outright. Acknowledging early cost
// a whole build: the verificator ran further than before and then hung at REG X000.
//
// It must also not FALL until this module is idle again. On a write the SDRAM's own busy drops while
// S_WR is still finishing, and ASIC.vhd reads that as "access over": it goes PRS_END -> PRS_IDLE and
// raises the strobes for the NEXT access while the cache is still occupied. The request edge is then
// gone by the time S_IDLE looks for it - either lost outright (the sub-CPU waits for a /DTACK that
// never comes: exactly the hardware hang, subA stuck with AS_N=0 and DTACK_N=1) or, if busy happens
// to still be high from a tail, answered with the PREVIOUS access's data. Both were reproduced in
// scratch/sim/tb_prg_cache.sv.
//
// So: high while initialising, high while the SDRAM is serving us, and high through the tail that
// both keeps read data stable and covers the rest of this module's work - never in between.
// and it must never DIP, not even for one clock. When the SDRAM finished a miss, busy was
// (state==S_HIT)|s_busy: s_busy had just fallen and S_HIT had not yet been entered, so busy went low
// for exactly one clk_ram cycle. clk_sys edges land on every other clk_ram edge, so about half the
// time ASIC.vhd's PRS_READ sampled that dip, decided the access was over, and latched PRG_DI in the
// same clock dout_r was still loading - every read came back with the PREVIOUS access's word. The
// simulation caught it as a clean off-by-one across every read.
//
// Reads may be marked busy from the very start: the ASIC only waits. WRITES may not, because
// PRS_WRITE drops the write strobes as soon as it sees busy, and sdram.sv still needs them - so the
// write path stays quiet until s_busy says the controller has taken it, then saw_busy carries it
// through to the tail without a gap.
wire busy_int = (state == S_INIT)
              | (state == S_LOOK) | (state == S_MISS) | (state == S_HIT)
              | (state == S_WR && saw_busy)
              | (state == S_TAIL)
              | s_busy;
assign busy = en ? busy_int : s_busy;

always @(posedge clk) begin
	old_rd <= rd;
	old_wr <= wr;
	we     <= 0;

	if (en && rd && !old_rd) pend_rd <= 1;
	if (en && wr && !old_wr) pend_wr <= 1;

	if (reset) begin
		state    <= S_INIT;
		icnt     <= 0;
		s_rd_r   <= 0;
		saw_busy <= 0;
		old_rd   <= 0;
		old_wr   <= 0;
		pend_rd  <= 0;
		pend_wr  <= 0;
	end
	else if (!en) begin
		// Parked while bypassed, and re-clears itself on the way back in: PRG-RAM will have moved
		// underneath us while the cache was not watching the port.
		state    <= S_INIT;
		icnt     <= 0;
		s_rd_r   <= 0;
		saw_busy <= 0;
		pend_rd  <= 0;
		pend_wr  <= 0;
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
			if (pend_rd || (en && rd && !old_rd)) begin
				pend_rd <= 0;
				q_idx <= idx; q_tag <= tag;
				state <= S_LOOK;
			end
			else if (pend_wr || (en && wr && !old_wr)) begin
				pend_wr <= 0;
				q_idx <= idx; q_tag <= tag;
				q_din <= din; q_wrl <= wrl; q_wrh <= wrh;
				state <= S_WR;
			end
		end

		S_LOOK: begin
			if (hit && !nohit) begin
				dout_r <= q[15:0];
				// A HIT ANSWERS FAST, and that is the point. Real PRG-RAM gives the sub-CPU no wait
				// states; ours measured 93 ns at best and 335 ns at worst from /AS to /DTACK against
				// a 120 ns deadline (telemetry beat 3), so the sub-CPU was losing cycles it should
				// never lose. Both remaining verificator failures are that same deficit read two
				// ways: VAR TESTS counts main-CPU polls across a sub-CPU-timed interval and reads
				// 27945 against a pass range of 23753-23980 (mcd-verificator @0x0189F0), and IRQ
				// sub-test 6 needs the sub-CPU's INT2 handler to keep up with 128 IFL2 pulses and
				// it only manages 69-126 (@0x018348). Three clocks is the shortest hold the gate
				// array can still see - clk_sys samples every second clk_ram - and dout_r is loaded
				// on the way in, so the data is stable for the whole of it.
				hcnt   <= 4'd2;          // S_LOOK + 3 = 4 clk_ram, ~37 ns instead of ~93 ns
				state  <= S_HIT;
			end
			else begin
				s_rd_r <= 1;
				state  <= S_MISS;
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
				s_rd_r <= 0;
				// Do NOT drop busy in the same cycle dout_r loads. ASIC.vhd's PRS_READ latches
				// PRG_DI on the clock where it sees PRG_RDY go high, and clk_sys edges coincide
				// with every other clk_ram edge, so it would latch the PREVIOUS word. sdram.sv
				// holds its own busy two extra cycles after capturing data for exactly this
				// reason (sdram.sv:120-127, and the matching multicycle in MegaCD.sdc); borrow
				// the hit path's counter to do the same here.
				hcnt  <= 4'd3;
				state <= S_HIT;
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
				hcnt  <= 4'd2;
				state <= S_TAIL;
			end
		end

		S_TAIL: begin
			hcnt <= hcnt - 1'd1;
			if (!hcnt) state <= S_IDLE;
		end

		default: state <= S_IDLE;
	endcase
end

endmodule
