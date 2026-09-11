# Defects found in the imported 32X / SH7604 RTL

Found while building a combined Mega Drive + Mega CD + 32X core. All of these are in RTL we
**imported unmodified**; each was discovered because the Mega CD adds bus contention the standalone
32X core never sees, but three of the five are latent everywhere.

**Provenance caveat, stated up front:** srg320's published `S32X_MiSTer` repo does not ship the 32X
interface RTL (`IF.sv`, `32X.sv`, `SH/SH7604/*`) — only `GEN/`, `CART/` and `FX68K/` — so I could
not diff these against a published upstream. What I can show is that each fix's patch script records
the exact pre-existing text as its anchor, and none of that text was written by us. Treat the
attribution as strong but unconfirmed, and check against your own tree before acting.

Line numbers are from our tree. Every claim below was measured on a DE10-Nano, not inferred.

---

## 1. The SH-2 cartridge read never waits for the SDRAM to acknowledge  (most serious)

The cartridge arbiter serves both CPUs. Only one of them checks that its request was accepted:

```systemverilog
IF.sv:908  RS_MD_WAIT: if (ROM_WAIT_SYNC)                                  // waits for the ACK
IF.sv:866  RS_SH_WAIT: if (/*(ROM_WAIT_SYNC || !USE_ROM_WAIT) &&*/ CE_F)   // ACK COMMENTED OUT
```

The SH-2 path advances to `RS_SH_READ` on a fixed timer — two `CE_F` periods, ~75–93 ns — without
confirming the SDRAM took the request. `sdram.sv` only accepts a request at a `clk_ram` edge where
`state == STATE_IDLE`, and it tests refresh **before** port 0 in the same else-if chain. Standalone,
the controller is idle when the strobe arrives and accepts within ~1 `clk_ram`, so the fixed delay
works by luck. Add competing ports and acceptance slips to 8–14 `clk_ram`, past the timer:
`RS_SH_READ` is entered with `ROM_WAIT` still low and captures the **previous** transaction's word.

Measured: the master SH-2 loads a function pointer from a PC-relative longword literal and jumps
through it. Expected values read directly out of the game ROM:

| instruction | ROM contains | SH-2 got |
|---|---|---|
| `0201DC34 mov.l 0x201dce8,r14` | `0201F284` | `00000001` |
| `0201C57C mov.l 0x201c5b0,r5`  | `02017E38` | `00000012` |
| `0201DC5C mov.l 0x201dcfc,r2`  | `0201F6EC` | `00002E01` |

**Fix:** restore the qualifier so the SH-2 waits for `ROM_WAIT` to rise, mirroring `RS_MD_WAIT`.
Keep an escape for cycles nothing answers (see #2) or it deadlocks.

Result: eight consecutive boots, zero wild jumps (previously frequent), and a title that had never
booted now runs.

---

## 2. `RS_MD_WAIT` deadlocks on a cycle the cartridge never answers

`RS_MD_WAIT` waits for `ROM_WAIT` to rise, but some cycles produce no SDRAM request at all, so it
never does and **both SH-2s park permanently**. `ba.sv:595` asserts `/CAS0` on reads only and
`cart.sv:244` ties the ROM write strobes off for a normal cartridge, so an MD **write** into the
`$880000-$9FFFFF` 32X ROM window generates nothing.

**Fix:** escape when `!CART_EXT` — i.e. nothing behind the connector is fetching or storing for this
cycle, so `ROM_WAIT` can never rise.

---

## 3. The 68000's raw cartridge strobes leak past the arbiter

`sdram.sv` starts a transaction on a **rising edge only** (`~old_rd[0] && rd[0]`, with `old_rd`
held while the strobe stays high), but the cartridge strobe muxes are qualified by `&& S32X_CE0`:

```systemverilog
IF.sv:1134  assign CCE0_N  = ADCR.ADEN && !DCR.RV && S32X_CE0 ? ~S32X_CE0  : MD_BIOS_SEL | CE0_N_SYNC[0];
IF.sv:1135  assign CCAS0_N = ADCR.ADEN && !DCR.RV && S32X_CE0 ? ~S32X_CAS0 : CAS0_N_SYNC[0];
cart.sv:243 assign ROM_RD  = ROM_ACCESS & ~CAS0_N;
```

so between grants the MD's raw `/CE0` and `/CAS0` reach the cartridge with the MD's address. If the
controller accepts that unarbitrated read, `rd0` is **already high** when the SH-2 is granted — the
SH-2's request produces no edge, is never issued, and it captures the 68000's word from the 68000's
address. Plausible-looking wrong data, which is worse than obvious garbage.

**Fix:** when the adapter owns the bus (`ADCR.ADEN && !DCR.RV`), drive `CCE0_N`/`CCAS0_N` from the
arbiter only. Leave `CASEL_N`/`CLWR_N`/`CUWR_N` qualified — the arbiter never grants for register
cycles like `$A130F1`, and gating those breaks SRAM banking.

Note `cart.sv:85`: `ROM_LIN_EN = (rom_sz > 'h400000)` forces `ROM_ACCESS` permanently high, so on
any cartridge larger than 4 MB this leak runs continuously.

---

## 4. SH7604 watchdog counts at φ/8 when `WTCSR.CKS = 000` selects φ/2

`SH7604.sv` wired the WDT's `CLK2_CE` input to `CLK8_CE` — a 4× error on the `CKS=000` tap. Harmless
until software uses the watchdog as a timer, which d32xr does (`pri_wdt_irq`, levels 2 & 3).

**Fix:** add the real φ/2 tap and connect it. The other taps (including `CLK4096_CE`, the one d32xr
actually selects) are correct.

---

## 5. PWM FIFO stops draining when the output mode is off

`IF.sv` halted the entire PWM timebase when `PWMCR.LMD == RMD == 0`, so the FIFO could never drain,
`FULL` latched, DREQ never asserted, and a PWM DMA never completed. PicoDrive's `consume_fifo_do()`
(`pico/32x/pwm.c`) advances the FIFO on elapsed cycles alone and never consults the output mode.

Measured: the master spun forever on `mov.l @r3,r0 / tst #2,r0 / bt` with `r3 = 0xFFFFFF9C`
(SH7604 DMAC `CHCR1`), waiting for TE on a DMA that could not finish.

**Fix:** keep the FIFO draining on elapsed cycles; gate only the DAC output on the mode bits.

---

## 6. (`sdram.sv`, MiSTer-generic) one `dout` register shared by all five ports

```systemverilog
sdram.sv:134  reg [15:0] dout;
sdram.sv:136  assign dout0 = dout;  ... dout1 ... dout2 ... dout3 ... dout4
sdram.sv:227  if (state == STATE_READY && ram_req) dout <= SDRAM_DQ;
```

A port's data survives only until **any** other port completes a read, so every consumer has to race
to latch it. Fine with one active master; a real hazard with five.

**Fix:** `ram_req` is already one-hot for the port being served, so give each port its own register.
Do **not** capture `SDRAM_DQ` into five enabled registers directly — we built that and the core came
up dead, because the `SDRAM_DQ` input path is tight and fanning it out breaks the capture. Keep the
single capture register and distribute one cycle later; `busy` stays high for three cycles after
`STATE_READY`, so there is room.
