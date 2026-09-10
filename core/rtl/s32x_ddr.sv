//============================================================================
//  32X external memories in the HPS DDR3: SH-2 work RAM (256 KB) and the two
//  128 KB frame buffers.
//
//  Why DDR3 and not the SDRAM: the DE10-Nano SDRAM controller moves one 16-bit
//  word per ~7 clocks; the MD cartridge, Mega CD PRG-RAM and PCM traffic plus
//  two 32X frame buffers would run it at ~90 % in the CD32X case
//  (phase0/BANDWIDTH.md). The DDR3 bridge bursts up to 255 x 64 bits, so a whole
//  scanline of frame buffer is one ~1 us request.
//
//  Ports (all on clk = clk_sys, DDRAM_CLK = clk_sys):
//   * sdr_*  SH-2 work RAM, 16-bit, ddram.sv semantics (edge-triggered rd/wr,
//            busy while outstanding, 16-byte read cache) - what S32X_MiSTer
//            does for this memory today, just on this clock.
//   * fbd_*  frame-buffer DRAW port (SH-2 / 68000 window / auto-fill through the
//            32X VDP): writes go into an 8-entry FIFO (fbd_busy = FIFO full),
//            reads return through a 16-byte cache with an fbd_rdy pulse.
//   * lp_*   frame-buffer DISPLAY prefetch: on lp_req the line-table entry for
//            line lp_line of buffer lp_fb is read, then the 320+ words that
//            start there are burst into the line buffer; lb_* is the VDP's
//            read side (index = FB word address - lp_base).
//
//  Accepted deviation (hardware limitation: external memory latency): the real
//  32X VDP reads the line-table entry at the first active pixel and the pixels
//  just in time; here both are read during the preceding HBLANK (~10 us
//  earlier). Only software racing the beam within one line can tell.
//
//  DDR3 map (byte offsets inside the core's 0x30000000 window):
//   0x000000 - 0x03FFFF  SH-2 work RAM (256 KB)
//   0x100000 - 0x11FFFF  frame buffer 0 (128 KB)
//   0x120000 - 0x13FFFF  frame buffer 1 (128 KB)
//  A 64-bit beat holds four 16-bit words, word 0 in bits 63:48 (big-endian word
//  order, matching ddram.sv).
//============================================================================

module s32x_ddr
(
	input             clk,
	input             reset,

	// HPS DDR3 bridge
	output            DDRAM_CLK,
	input             DDRAM_BUSY,
	output      [7:0] DDRAM_BURSTCNT,
	output     [28:0] DDRAM_ADDR,
	input      [63:0] DDRAM_DOUT,
	input             DDRAM_DOUT_READY,
	output            DDRAM_RD,
	output     [63:0] DDRAM_DIN,
	output      [7:0] DDRAM_BE,
	output            DDRAM_WE,

	// SH-2 work RAM (16-bit words)
	input      [17:1] sdr_addr,
	input      [15:0] sdr_din,
	output     [15:0] sdr_dout,
	input             sdr_rd,
	input       [1:0] sdr_wr,
	output            sdr_busy,

	// frame-buffer draw port: buffer select + 16-bit word address
	input             fbd_fb,
	input      [15:0] fbd_addr,
	input      [15:0] fbd_din,
	output     [15:0] fbd_dout,
	input             fbd_rd,       // level (rising edge starts a read)
	input       [1:0] fbd_wr,       // level (rising edge queues a write), byte enables
	output            fbd_busy,     // write FIFO full: hold the VDP's FIFO drain / auto-fill
	output reg        fbd_rdy,      // one-clock pulse: fbd_dout valid for the last read

	// display line prefetch
	input             lp_req,       // pulse (during HBLANK)
	input             lp_fb,        // buffer being displayed
	input       [7:0] lp_line,      // line-table index (V_CNT)
	output reg [15:0] lp_start,     // the table entry: word address the line starts at
	output reg [15:0] lp_base,      // lp_start rounded down to a 4-word beat: line-buffer index 0
	output reg        lp_done,      // pulse: the line buffer holds the line

	// line buffer read side (VDP display stream)
	input       [8:0] lb_addr,      // word index relative to lp_base (0..323)
	output     [15:0] lb_q,         // registered: valid the clock after lb_addr

	input      [63:0] tel_audio     // audio peaks + sample-enable count (tools/phase3_audio_probe.py)
);

assign DDRAM_CLK = clk;

// 64-bit beat indices (byte address / 8) inside the 0x30000000 window
localparam [24:0] BASE_SDR = 25'h0000000;
localparam [24:0] BASE_FB0 = 25'h0020000;   // 0x100000 / 8
localparam [24:0] BASE_FB1 = 25'h0024000;   // 0x120000 / 8
localparam [14:0] FB_BEATS = 15'd16384;     // 128 KB / 8
localparam [24:0] BASE_TEL = 25'h0040000;   // 0x200000 / 8: one telemetry beat (see tools/phase2_telemetry.py)
localparam        TELEMETRY = 1;
localparam  [6:0] LP_BEATS = 7'd81;         // 324 words from the beat holding lp_start: >= 320 at any alignment

//----------------------------------------------------------------------------
// helpers
function [15:0] pick16(input [127:0] line, input [2:0] idx);
	case (idx)
		3'd0: pick16 = line[127:112];
		3'd1: pick16 = line[111:96];
		3'd2: pick16 = line[95:80];
		3'd3: pick16 = line[79:64];
		3'd4: pick16 = line[63:48];
		3'd5: pick16 = line[47:32];
		3'd6: pick16 = line[31:16];
		3'd7: pick16 = line[15:0];
	endcase
endfunction

function [15:0] pick16b(input [63:0] beat, input [1:0] idx);
	case (idx)
		2'd0: pick16b = beat[63:48];
		2'd1: pick16b = beat[47:32];
		2'd2: pick16b = beat[31:16];
		2'd3: pick16b = beat[15:0];
	endcase
endfunction

function [7:0] be16(input [1:0] be, input [1:0] w);
	case (w)
		2'd0: be16 = {be, 6'b000000};
		2'd1: be16 = {2'b00, be, 4'b0000};
		2'd2: be16 = {4'b0000, be, 2'b00};
		2'd3: be16 = {6'b000000, be};
	endcase
endfunction

function [127:0] upd16(input [127:0] line, input [2:0] idx, input [15:0] d, input [1:0] be);
	reg [127:0] r; reg [15:0] w;
	begin
		r = line;
		w = pick16(line, idx);
		if (be[1]) w[15:8] = d[15:8];
		if (be[0]) w[7:0]  = d[7:0];
		case (idx)
			3'd0: r[127:112] = w;
			3'd1: r[111:96]  = w;
			3'd2: r[95:80]   = w;
			3'd3: r[79:64]   = w;
			3'd4: r[63:48]   = w;
			3'd5: r[47:32]   = w;
			3'd6: r[31:16]   = w;
			3'd7: r[15:0]    = w;
		endcase
		upd16 = r;
	end
endfunction

//----------------------------------------------------------------------------
// SH-2 RAM: one 16-byte cache line (ddram.sv scheme)
reg  [17:4] sdr_cache_a = '1;
reg         sdr_cache_v = 0;
reg [127:0] sdr_cache_d;
reg         sdr_rd_pend = 0, sdr_wr_pend = 0;
reg  [17:1] sdr_a_q;
reg  [15:0] sdr_d_q;
reg   [1:0] sdr_be_q;
assign sdr_busy = sdr_rd_pend | sdr_wr_pend;
// Index the line with the LIVE address while a read is asserted. sdr_a_q is only loaded on the rising
// edge of sdr_rd, which is one clk_sys too late for the second and later beats of an SH-2 cache-line
// burst: the BSC re-drives the address and RD_N on its CE_R half and latches the data on the very next
// CE_F half without re-checking WAIT_N, so the mux was still showing the previous beat's word and the
// line filled as w0,w0,w1,w2,... Upstream's ddram.sv escapes this only by running on clk_ram (twice
// this clock), where the registered index settles inside the same bus cycle.
assign sdr_dout = pick16(sdr_cache_d, sdr_rd ? sdr_addr[3:1] : sdr_a_q[3:1]);

// draw read: one 16-byte cache line, tagged with {buffer, word address}
// fbd_addr is a WORD index (0..65535 = 128 KB), unlike sdr_addr which is a byte address with bit 0
// dropped: a 16-byte cache line is 8 words selected by fbd_addr[2:0], the tag is fbd_addr[15:3], and a
// beat holds 4 words at fbd_addr[1:0]. The write path already used that numbering while the read path
// used the byte-address numbering, so reads took the wrong word and compared a tag built from different
// bits than the one they stored. fbd_ra_q must also be 17 bits - {fbd_fb, fbd_addr} is 1+16, and
// truncating it dropped the buffer-select bit, so a read could come from the buffer being displayed.
reg  [16:3] fbd_cache_a = '1;
reg         fbd_cache_v = 0;
reg [127:0] fbd_cache_d;
reg         fbd_rd_pend = 0;
reg  [16:0] fbd_ra_q;
assign fbd_dout = pick16(fbd_cache_d, fbd_ra_q[2:0]);

// draw write FIFO: {fb, addr[15:0], be[1:0], data[15:0]}
(* ramstyle = "logic" *) reg [34:0] wfifo[8];
reg   [2:0] wf_wp = 0, wf_rp = 0;
wire  [2:0] wf_cnt   = wf_wp - wf_rp;
wire        wf_empty = (wf_cnt == 3'd0);
wire        wf_full  = (wf_cnt == 3'd7);
assign fbd_busy = (wf_cnt >= 3'd6);   // two slots of slack: the VDP checks busy one clock before its write edge arrives
wire [34:0] wf_head = wfifo[wf_rp];
wire        wf_fb   = wf_head[34];
wire [15:0] wf_addr = wf_head[33:18];
wire  [1:0] wf_be   = wf_head[17:16];
wire [15:0] wf_data = wf_head[15:0];

//----------------------------------------------------------------------------
// line buffer: 128 beats x 64 bits (one M10K), written one beat per clock as
// the burst arrives, read as 16-bit words by the VDP
reg  [63:0] linebuf[128];
reg   [6:0] lb_wa = 0;
reg         lb_we = 0;
reg  [63:0] lb_wd;
reg  [63:0] lb_rd_beat;
reg   [1:0] lb_rd_idx;
always @(posedge clk) begin
	if (lb_we) linebuf[lb_wa] <= lb_wd;
	lb_rd_beat <= linebuf[lb_addr[8:2]];
	lb_rd_idx  <= lb_addr[1:0];
end
assign lb_q = pick16b(lb_rd_beat, lb_rd_idx);

//----------------------------------------------------------------------------
// DDR3 request machine
localparam S_IDLE = 3'd0, S_WR = 3'd1, S_RD_LINE = 3'd2, S_LP_TAB = 3'd3, S_LP_BURST = 3'd4;
reg   [2:0] state = S_IDLE;
reg         kind;                    // read-line owner: 0 SH-2 RAM, 1 draw
reg  [24:0] ram_addr;
reg   [7:0] ram_burst;
reg  [63:0] ram_din;
reg   [7:0] ram_be;
reg         ram_rd = 0, ram_wr = 0;
reg         beat;
reg         lp_pend = 0, lp_fb_q;
// telemetry counters
reg  [15:0] tel_seq = 0;
reg   [7:0] tel_sdr_rd = 0, tel_sdr_wr = 0, tel_fbd_wr = 0, tel_lp = 0;
reg  [16:0] tel_timer = 0;
reg   [1:0] tel_pend = 0;    // 2 = counters beat, 1 = audio beat
reg   [7:0] lp_line_q;
reg   [1:0] lp_tab_idx;
reg         lp_go = 0;               // table entry captured: issue the line burst
reg         lp_go2 = 0;              // first burst done, second (wrapped) burst to issue
reg   [6:0] lp_beats_left;
reg   [6:0] lp_beats_2nd;            // beats of the second burst after a wrap at the buffer end (0 = none)
reg  [13:0] lp_beat;                 // first beat of the line inside the buffer

assign DDRAM_ADDR     = {4'b0011, ram_addr};
assign DDRAM_BURSTCNT = ram_burst;
assign DDRAM_RD       = ram_rd;
assign DDRAM_WE       = ram_wr;
assign DDRAM_DIN      = ram_din;
assign DDRAM_BE       = ram_be;

wire [15:0] tab_entry = pick16b(DDRAM_DOUT, lp_tab_idx);
wire [24:0] fb_base   = lp_fb_q ? BASE_FB1 : BASE_FB0;
wire [14:0] lp_room   = FB_BEATS - {1'b0, lp_beat};       // beats from the line start to the end of the buffer

always @(posedge clk) begin
	reg old_sdr_rd, old_sdr_wr, old_fbd_rd, old_fbd_wr;

	old_sdr_rd <= sdr_rd;
	old_sdr_wr <= |sdr_wr;
	old_fbd_rd <= fbd_rd;
	old_fbd_wr <= |fbd_wr;

	fbd_rdy <= 0;
	lp_done <= 0;
	lb_we   <= 0;
	if (lb_we) lb_wa <= lb_wa + 1'd1;   // advance after every stored beat

	// ---- accept SH-2 RAM requests (edge-triggered, like ddram.sv)
	if (sdr_rd && !old_sdr_rd && !sdr_busy) begin
		sdr_a_q <= sdr_addr;
		if (!(sdr_cache_v && sdr_cache_a == sdr_addr[17:4])) sdr_rd_pend <= 1;
	end
	if (|sdr_wr && !old_sdr_wr && !sdr_busy) begin
		sdr_a_q  <= sdr_addr;
		sdr_d_q  <= sdr_din;
		sdr_be_q <= sdr_wr;
		sdr_wr_pend <= 1;
		if (sdr_cache_v && sdr_cache_a == sdr_addr[17:4]) sdr_cache_d <= upd16(sdr_cache_d, sdr_addr[3:1], sdr_din, sdr_wr);
	end

	// ---- accept draw requests
	if (fbd_rd && !old_fbd_rd && !fbd_rd_pend) begin
		fbd_ra_q <= {fbd_fb, fbd_addr};
		if (fbd_cache_v && fbd_cache_a == {fbd_fb, fbd_addr[15:3]}) fbd_rdy <= 1;
		else fbd_rd_pend <= 1;
	end
	if (|fbd_wr && !old_fbd_wr && !wf_full) begin
		wfifo[wf_wp] <= {fbd_fb, fbd_addr, fbd_wr, fbd_din};
		wf_wp <= wf_wp + 1'd1;
		if (fbd_cache_v && fbd_cache_a == {fbd_fb, fbd_addr[15:3]}) fbd_cache_d <= upd16(fbd_cache_d, fbd_addr[2:0], fbd_din, fbd_wr);
	end

	// ---- prefetch request
	if (lp_req) begin
		lp_pend   <= 1;
		lp_fb_q   <= lp_fb;
		lp_line_q <= lp_line;
	end

	// telemetry: count the traffic and ask for a write every ~1.2 ms
	if (TELEMETRY) begin
		if (sdr_rd && !old_sdr_rd) tel_sdr_rd <= tel_sdr_rd + 1'd1;
		if (|sdr_wr && !old_sdr_wr) tel_sdr_wr <= tel_sdr_wr + 1'd1;
		if (|fbd_wr && !old_fbd_wr) tel_fbd_wr <= tel_fbd_wr + 1'd1;
		if (lp_done) tel_lp <= tel_lp + 1'd1;
		tel_timer <= tel_timer + 1'd1;
		if (&tel_timer) tel_pend <= 2'd2;
	end

	// ---- returning data (independent of DDRAM_BUSY)
	if (DDRAM_DOUT_READY) begin
		case (state)
		S_RD_LINE: begin
			if (!kind) begin
				if (!beat) sdr_cache_d[127:64] <= DDRAM_DOUT; else sdr_cache_d[63:0] <= DDRAM_DOUT;
			end else begin
				if (!beat) fbd_cache_d[127:64] <= DDRAM_DOUT; else fbd_cache_d[63:0] <= DDRAM_DOUT;
			end
			beat <= 1;
			if (beat) begin
				if (!kind) begin sdr_cache_v <= 1; sdr_rd_pend <= 0; end
				else       begin fbd_cache_v <= 1; fbd_rd_pend <= 0; fbd_rdy <= 1; end
				state <= S_IDLE;
			end
		end

		S_LP_TAB: begin
			lp_start <= tab_entry;
			lp_base  <= {tab_entry[15:2], 2'b00};
			lp_beat  <= tab_entry[15:2];
			lb_wa    <= 0;
			lp_go    <= 1;
		end

		S_LP_BURST: begin
			lb_we <= 1;
			lb_wd <= DDRAM_DOUT;
			lp_beats_left <= lp_beats_left - 1'd1;
			if (lp_beats_left == 1) begin
				if (lp_beats_2nd != 0) begin
					lp_go2 <= 1;                     // wrapped at the buffer end: fetch the rest from its start
				end else begin
					lp_done <= 1;
					state   <= S_IDLE;
				end
			end
		end
		default: ;
		endcase
	end

	// ---- issuing requests (Avalon: hold rd/wr until DDRAM_BUSY is low)
	if (reset) begin
		state <= S_IDLE; ram_rd <= 0; ram_wr <= 0;
		sdr_rd_pend <= 0; sdr_wr_pend <= 0; fbd_rd_pend <= 0;
		sdr_cache_v <= 0; fbd_cache_v <= 0;
		wf_wp <= 0; wf_rp <= 0; lp_pend <= 0; lp_go <= 0; lp_go2 <= 0;
	end
	else if (!DDRAM_BUSY) begin
		ram_rd <= 0;
		ram_wr <= 0;
		case (state)
		S_IDLE: begin
			// priority: display prefetch (deadline) > queued draw writes > SH-2 write > draw read > SH-2 read
			if (TELEMETRY && |tel_pend) begin
				tel_pend  <= tel_pend - 1'd1;
				ram_be    <= 8'hFF;
				ram_burst <= 8'd1;
				ram_wr    <= 1;
				state     <= S_WR;
				if (tel_pend == 2'd2) begin
					tel_seq  <= tel_seq + 1'd1;
					ram_addr <= BASE_TEL;
					ram_din  <= {16'h5332, tel_seq, tel_sdr_rd, tel_sdr_wr, tel_fbd_wr, tel_lp};
				end else begin
					ram_addr <= BASE_TEL + 25'd1;
					ram_din  <= tel_audio;
				end
			end
			else if (lp_pend) begin
				lp_pend    <= 0;
				lp_tab_idx <= lp_line_q[1:0];
				ram_addr   <= fb_base + {19'd0, lp_line_q[7:2]};   // the table entry is word lp_line of the buffer
				ram_burst  <= 8'd1;
				ram_rd     <= 1;
				state      <= S_LP_TAB;
			end
			else if (!wf_empty) begin
				ram_addr  <= (wf_fb ? BASE_FB1 : BASE_FB0) + {11'd0, wf_addr[15:2]};
				ram_din   <= {4{wf_data}};
				ram_be    <= be16(wf_be, wf_addr[1:0]);
				ram_burst <= 8'd1;
				ram_wr    <= 1;
				wf_rp     <= wf_rp + 1'd1;
				state     <= S_WR;
			end
			else if (sdr_wr_pend) begin
				ram_addr  <= BASE_SDR + {10'd0, sdr_a_q[17:3]};
				ram_din   <= {4{sdr_d_q}};
				ram_be    <= be16(sdr_be_q, sdr_a_q[2:1]);
				ram_burst <= 8'd1;
				ram_wr    <= 1;
				sdr_wr_pend <= 0;
				state     <= S_WR;
			end
			else if (fbd_rd_pend) begin
				ram_addr    <= (fbd_ra_q[16] ? BASE_FB1 : BASE_FB0) + {11'd0, fbd_ra_q[15:3], 1'b0};
				ram_burst   <= 8'd2;
				ram_rd      <= 1;
				kind        <= 1;
				beat        <= 0;
				fbd_cache_a <= fbd_ra_q[16:3];
				fbd_cache_v <= 0;
				state       <= S_RD_LINE;
			end
			else if (sdr_rd_pend) begin
				ram_addr    <= BASE_SDR + {10'd0, sdr_a_q[17:4], 1'b0};
				ram_burst   <= 8'd2;
				ram_rd      <= 1;
				kind        <= 0;
				beat        <= 0;
				sdr_cache_a <= sdr_a_q[17:4];
				sdr_cache_v <= 0;
				state       <= S_RD_LINE;
			end
		end

		S_WR: state <= S_IDLE;   // accepted: WE was high while DDRAM_BUSY was low

		S_LP_TAB: if (lp_go) begin
			lp_go    <= 0;
			ram_addr <= fb_base + {11'd0, lp_beat};
			ram_rd   <= 1;
			if (lp_room >= {8'd0, LP_BEATS}) begin
				ram_burst     <= {1'b0, LP_BEATS};
				lp_beats_left <= LP_BEATS;
				lp_beats_2nd  <= 0;
			end else begin
				ram_burst     <= {1'b0, lp_room[6:0]};
				lp_beats_left <= lp_room[6:0];
				lp_beats_2nd  <= LP_BEATS - lp_room[6:0];
			end
			state <= S_LP_BURST;
		end

		S_LP_BURST: if (lp_go2) begin
			lp_go2        <= 0;
			ram_addr      <= fb_base;
			ram_burst     <= {1'b0, lp_beats_2nd};
			lp_beats_left <= lp_beats_2nd;
			lp_beats_2nd  <= 0;
			ram_rd        <= 1;
		end
		default: ;
		endcase
	end
end

endmodule
