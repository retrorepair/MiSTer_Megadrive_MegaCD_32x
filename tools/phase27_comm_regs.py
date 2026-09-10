#!/usr/bin/env python3
"""Expose the 32X comm registers and PWM status, to settle the Fusion rendezvous.

WHY
Both SH-2s are in tight spin loops in Fusion's own cart ROM, disassembled from the ROM itself:

    MASTER 0201DD5A   mov.w @r7,r13 ; tst r13,r13 ; bf .     r7 = 0x20004024  (COMM, SH-2 side)
    SLAVE  0201E5CE   mov.w @r8,r2  ; cmp/pz r2   ; bf .     then mov.w r10,@r8

The master waits for a comm register to read ZERO; the slave waits for bit 15 of a register to
CLEAR and then pushes a value - the shape of the PWM FIFO FULL flag. Meanwhile the 68000 is alive
and hitting $A151xx ~27k/s, i.e. sitting in d32xr's main_loop, which polls $A15120 (COMM0) and
$A15124 (COMM4) for requests and writes 0 back when it has serviced one.

So all three CPUs are alive and the rendezvous never completes. Every register path involved -
CP0R..CP7R both directions, the PWM FIFO, DCR/ADCR/BSR - has been diffed against pristine upstream
32X/IF.sv and is byte-identical, so this is not a transcription error and guessing further is
pointless. Read the actual values.

Beat 6 at DDR3 0x30200030:
       [63:48] CP0R   COMM0 - master request channel in d32xr
       [47:32] CP2R   COMM2
       [31:16] CP4R   COMM4 - what the master is polling at 0x20004024
       [15:0]  {LPWR.FULL, LPWR.EMPTY, RPWR.FULL, RPWR.EMPTY, PWMCR[11:0]}

Readings and what they mean:
  CP4R non-zero and stuck  -> the master posted a request the 68000 never cleared: look at why
                              main_loop never reaches main_loop_handle_req (scd_flush_cmd_queue
                              blocking on $A1200F is the prime suspect)
  CP4R zero                -> the master's write is not landing, or its read is not seeing it
  LPWR.FULL stuck at 1     -> the PWM FIFO never drains, which alone explains the slave loop;
                              check PWMCR.LMD/RMD, since IF.sv:695 only advances the FIFO when
                              one of them is set

Usage: phase27_comm_regs.py <core dir>"""
import sys, os

d = sys.argv[1]


def edit(rel, pairs):
    p = os.path.join(d, rel)
    s = open(p, encoding="utf-8", errors="replace").read()
    for old, new in pairs:
        assert old in s, rel + ": anchor missing: " + old[:70]
        assert s.count(old) == 1, rel + ": anchor not unique: " + old[:70]
        s = s.replace(old, new, 1)
    open(p, "w", encoding="utf-8", newline="").write(s)
    print(rel, "ok")


edit("rtl/S32X/IF.sv", [
    ("""	output            SH_CP_WRITE
);""",
     """	output            SH_CP_WRITE,
	output     [63:0] DBG_COMM		// tools/phase27_comm_regs.py
);"""),
    # d32xr names comm registers by BYTE OFFSET, so its COMM0/COMM2/COMM4 are $A15120/$A15122/
    # $A15124 = our CP0R/CP1R/CP2R. The master polls SH-2 $20004024, which is CP2R.
    ("""	assign CASEL_N = """,
     """	assign DBG_COMM = {CP0R, CP1R, CP2R,
	                   LPWR.FULL, LPWR.EMPTY, RPWR.FULL, RPWR.EMPTY, PWMCR[11:0]};

	assign CASEL_N = """),
])

edit("rtl/S32X/32X.sv", [
    ("""	output     [31:0] DBG_SSH_PC
);""",
     """	output     [31:0] DBG_SSH_PC,
	output     [63:0] DBG_COMM			// tools/phase27_comm_regs.py
);"""),
    ("""		.CART_EXT(CART_EXT)""",
     """		.CART_EXT(CART_EXT),
		.DBG_COMM(DBG_COMM)"""),
])

edit("MegaCD.sv", [
    ("""	.DBG_MSH_PC(S32X_MSH_PC),""",
     """	.DBG_COMM(S32X_COMM),
	.DBG_MSH_PC(S32X_MSH_PC),"""),
    ("""wire [63:0] tel_md = {tel_md_cycles, tel_md_32xreg};""",
     """wire [63:0] tel_md = {tel_md_cycles, tel_md_32xreg};

// 32X comm registers and PWM status (tools/phase27_comm_regs.py). All three CPUs are alive but the
// master<->68000 rendezvous never completes, and every register path involved is byte-identical to
// upstream, so the values themselves are the only thing left to look at.
wire [63:0] S32X_COMM;
wire [63:0] tel_comm = S32X_COMM;"""),
    ("""	.tel_md(tel_md)
);""",
     """	.tel_md(tel_md),
	.tel_comm(tel_comm)
);"""),
])

edit("rtl/s32x_ddr.sv", [
    ("""	input      [63:0] tel_md        // MD 68000 bus cycles and $A151xx accesses
);""",
     """	input      [63:0] tel_md,       // MD 68000 bus cycles and $A151xx accesses
	input      [63:0] tel_comm      // 32X comm registers + PWM (tools/phase27_comm_regs.py)
);"""),
    ("reg   [2:0] tel_pend = 0;    // 5 = counters, 4 = audio, 3 = MCD bus, 2 = sector rate, 1 = SH-2 PCs",
     "reg   [2:0] tel_pend = 0;    // 7=counters 6=audio 5=MCDbus 4=sector 3=SH2PC 2=MD 1=comm"),
    ("\t\tif (&tel_timer) tel_pend <= 3'd6;",
     "\t\tif (&tel_timer) tel_pend <= 3'd7;"),
    ("""				if (tel_pend == 3'd6) begin""",
     """				if (tel_pend == 3'd7) begin"""),
    ("""				end else if (tel_pend == 3'd5) begin
					ram_addr <= BASE_TEL + 25'd1;""",
     """				end else if (tel_pend == 3'd6) begin
					ram_addr <= BASE_TEL + 25'd1;"""),
    ("""				end else if (tel_pend == 3'd4) begin
					ram_addr <= BASE_TEL + 25'd2;""",
     """				end else if (tel_pend == 3'd5) begin
					ram_addr <= BASE_TEL + 25'd2;"""),
    ("""				end else if (tel_pend == 3'd3) begin
					ram_addr <= BASE_TEL + 25'd3;""",
     """				end else if (tel_pend == 3'd4) begin
					ram_addr <= BASE_TEL + 25'd3;"""),
    ("""				end else if (tel_pend == 3'd2) begin
					ram_addr <= BASE_TEL + 25'd4;
					ram_din  <= tel_sh2pc;
				end else begin
					ram_addr <= BASE_TEL + 25'd5;
					ram_din  <= tel_md;
				end""",
     """				end else if (tel_pend == 3'd3) begin
					ram_addr <= BASE_TEL + 25'd4;
					ram_din  <= tel_sh2pc;
				end else if (tel_pend == 3'd2) begin
					ram_addr <= BASE_TEL + 25'd5;
					ram_din  <= tel_md;
				end else begin
					ram_addr <= BASE_TEL + 25'd6;
					ram_din  <= tel_comm;
				end"""),
])
