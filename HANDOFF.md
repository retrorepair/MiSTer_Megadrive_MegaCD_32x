# HANDOFF / ROADMAP — Mega Drive + Mega CD + 32X on MiSTer (DE10-Nano)

Written 2026-09-08, at the end of the NukedMD-MegaCD release work, by the agent that did that work.
This is a roadmap for a NEW core: a single MiSTer core that is a Mega Drive with a **32X in the
cartridge slot** and a **Mega CD on the expansion port** — the real "Sega CD 32X" stack — running all
three tiers of software (MD carts, Mega CD discs, 32X carts, and the six CD32X titles).

It is written to be honest about the one thing that decides everything: **the DE10-Nano's Cyclone V
5CSEBA6 is nearly full with just MD+MCD when the MD is the gate-level NukedMD.** Every number in §3
is measured from that core's fit report, not guessed. The conclusion is that the 32X core is
feasible, but only on a behavioural Mega Drive, with all 32X memory off-chip, and with the optional
extras stripped. The user has already accepted that NukedMD cannot be part of it; §3 shows why in
numbers.

Conventions: "MD" = Mega Drive/Genesis; "MCD" = Mega CD/Sega CD; "32X" = Super 32X/Sega 32X;
"S32X" = srg320's MiSTer 32X core; "M10K" = Cyclone V 10-kbit block RAM; "ALM" = adaptive logic module.

---

## 0. What the target hardware actually is

Physically the stack is: **Mega Drive** (68000 @7.67 MHz, VDP, Z80, YM2612/PSG) → **32X plugged into
the cartridge slot** (its own cart slot on top passes the game ROM through) → **Mega CD on the
expansion port** underneath. Electrically:

- The **32X is a cartridge-slot device**. It sits between the MD and the game ROM. It intercepts the
  MD's cartridge bus (/CE0, /CART, the address/data bus), maps its own registers into the MD's space
  (the "32X registers" at $A15100-$A1513F, the comm ports, the frame-buffer window at
  $840000-$85FFFF / overwrite $860000, and the SH-2 boot/vector area), and passes ordinary ROM
  accesses through to the cartridge behind it. It contains **two Hitachi SH-2 (SH7604) CPUs at
  23.011 MHz** (= 3× the MD 68000 clock, derived from the MD's master clock), a **32X VDP** with two
  **128 KB frame buffers** (15-bit direct colour, run-length and packed-pixel modes), a **PWM
  stereo audio unit**, 256 KB of shared SDRAM for the SH-2s, and a small boot ROM per CPU. Its video
  output is **overlaid on the MD's VDP output** (per-pixel priority via the MD's /YS line) — the 32X
  does not replace the MD picture, it composites on top of it, and the two are genlocked to the MD's
  master clock.
- The **Mega CD is an expansion-port device** (the port on the side/bottom): its own 68000
  (12.5 MHz), gate array (ASIC), CDC (LC8951), PCM (RF5C164), 512 KB PRG-RAM, 256 KB Word RAM,
  64 KB PCM RAM, BIOS ROM, and the CD drive. It is mapped at $400000 (BIOS/PRG/Word RAM window) and
  $A12000 (gate-array registers). Its audio (PCM + CDDA) is mixed into the console's audio path.
- **Reset is one shared line** across the three units (the front button warm-resets the console; the
  peripherals see it too) — see §8, this bit us hard.
- Software tiers: plain MD cart (32X and MCD present but idle), Mega CD disc (32X idle), 32X cart
  (MCD idle), and **CD32X** (Night Trap, Corpse Killer, Slam City, Supreme Warrior, Surgical Strike,
  Fahrenheit — the SH-2s run the game while the MCD streams the video). The last tier is the only one
  that exercises everything at once and is the acceptance test for the combined core.

## 1. What exists to build from (do not start from scratch)

| Piece | Where | What it gives |
|---|---|---|
| **srg320 `MegaCD_MiSTer`** (upstream) | `C:\Users\joelw\Documents\MegaCD_MiSTer_New\MegaCD_MiSTer-master_ORIG` (pristine copy) | fpgagen behavioural MD + the whole Mega CD block (`rtl/MCD`: ASIC, CDC, PCM, sub-68000, CEGen, SDRAM ports) + Main support. **This is the base.** |
| **srg320 `S32X_MiSTer`** | github.com/srg320/S32X_MiSTer (clone it) | fpgagen behavioural MD + the whole 32X block (two SH-2 cores, 32X VDP with frame buffers, PWM, the 32X-on-cart-bus glue and the video overlay). Same author, **same fpgagen MD**, so the two cores share their MD side almost line for line — this is what makes the merge tractable. |
| **This project: NukedMD-MegaCD** | `MegaCD_MiSTer-master` (this repo), HANDOFF.md / STATS.md / README.MD | The accuracy reference for MD behaviour (gate-level 68000/VDP/FM/Z80/FC1004), the mcd-verificator results (11/12 NTSC), the reset topology, the SDRAM 5-port design, the M10K squeeze tricks, and all the test tooling in `tools/mister`. **Not the base** — it does not fit with a 32X (§3) — but everything learnt here about the MCD block, Main and the hardware bring-up transfers. |
| **Main_MiSTer fork** | `retrorepair/Main_MiSTer`, branch `megacd-nukedmd` (master fast-forwarded) | The MegaCD Main patches (disc/eject/reset handling, line-buffered stdout). `support/s32x/` exists upstream for the 32X core. Both need to coexist in one core's Main support. |
| Test tooling | `MegaCD_MiSTer-master/tools/mister/` | `uinput_kbd.py` (virtual keyboard daemon), `osd.py` (blind OSD driver), `verif_loop.sh`, `cartdisc_test.sh`, `deploy.sh`, `hpsmem.py` (live DDR3 reads). Core-agnostic; reuse as-is. |
| Test software | on the MiSTer | mcd-verificator.bin; MD carts; MCD discs (Cobra Command etc.). **Need to add:** 32X carts (Virtua Racing Deluxe, Doom 32X, Knuckles Chaotix, Star Wars Arcade — good coverage), the 32X test ROMs, and at least one CD32X title. |

## 2. The one decision that has already been made

**The Mega Drive side is fpgagen (behavioural), not NukedMD.** Reasons, in order:
1. It does not fit otherwise — §3.
2. fpgagen is what both srg320 cores already use, so the merge is between two cores that share an MD,
   not a transplant.
3. fpgagen is "good enough" for the tiers that matter here: the 32X and CD32X titles are far less
   sensitive to MD sub-cycle timing than the mcd-verificator's interrupt-latency tests are. The
   accuracy the user cares about most for this core is the **32X** (SH-2 timing, frame-buffer swap
   timing, PWM) and the **MCD**, both of which are inherited wholesale.

What is lost: the NukedMD-MegaCD core passes verificator tests (VAR, REG 8030, IRQ 09) that depend on
the main 68000's exact cycle behaviour; fpgagen will likely fail one or more of those. That is an
accepted trade. Keep the NukedMD-MegaCD core as the "accurate MD+MCD" release and position the
32X core as "the stack", so nobody loses the accurate one.

## 3. The resource budget — measured, not estimated

Device: **Cyclone V 5CSEBA6U23I7** — 41,910 ALMs, 83,820 registers, **553 M10K blocks (5,662,720
bits)**, 112 DSP blocks, 6 PLLs.

### 3.1 What the NukedMD-MegaCD core uses today (build 65 fit report, `scratchpad/b65.fit.rpt`)

| Resource | Used / Available | |
|---|---|---|
| ALMs needed | **35,405 / 41,910 (84 %)** | placement actually occupies 38,900 (93 %); LABs 98 % used; packing difficulty "Medium" |
| Registers | 51,647 / 167,640 | not a constraint |
| **M10K blocks** | **519 / 553 (94 %)** | **34 blocks (≈340 kbit) free — this is the wall** |
| M10K bits | 4.11 Mbit data in 5.31 Mbit allocated | ~1.2 Mbit is packing waste (7 blocks per 64 kbit bank) |
| DSP | 56 / 112 | not a constraint |
| PLLs | 3 / 6 | fine |

Per-module (ALMs needed / M10K blocks):

| Block | ALMs | M10K | Notes |
|---|---|---|---|
| **`md_board` = NukedMD Mega Drive** | **13,392** | 70 | 68000 3,403 (+14 M10K microcode); VDP 4,883; VRAM 2,524 (+56 M10K); FM 988; Z80 996; IOC/arb/TMSS ~420 |
| **`MCD` = Mega CD block** | **7,805** | **293** | sub-68000 3,813 (+14 M10K); ASIC 1,714; PCM 499; CDC 199; Game Genie (sub) 1,161; **Word RAM 2×128 = 256 M10K**; CDC RAM 16; CDDA FIFO 7 |
| Framework (`sys_top` − `emu`) | 7,171 | 59 | ascal scaler 2,127 (+43 M10K); audio_out 1,074; OSDs 1,040 (+8); pll_hdmi_adj 536; misc |
| Other `emu` glue | ~7,037 | 38 | Game Genie (main) 1,159; hps_io 910; video_mixer 767 (+15, Hq2x); mcd_cart 577; TMSS ROM in LUTs 511; pll_cfg 514; audio_cond 496; video_freak 325; md_io 534; work RAM 64 M10K; Z80 RAM 8; backup RAM 8 |

### 3.2 What the 32X adds (to be MEASURED in Phase 0 by synthesising S32X_MiSTer; these are the
knowns and the expectations)

- **Two SH-2 cores.** The S32X core's SH-2 is a behavioural 32-bit RISC with a 5-stage pipeline,
  16-way? no — a 4 KB unified cache, MAC unit, DMAC, SCI, FRT, WDT, division unit and interrupt
  controller per CPU. Expect each to be **in the same class as a behavioural 68000 or larger** —
  budget **4,000–6,000 ALMs each** until measured, plus cache RAM (4 KB = ~4 M10K each if in
  block RAM) and possibly DSP for the MAC.
- **32X VDP**: line-mode/packed/RLE decoders, palette (256×16-bit = 4 kbit), the frame-buffer
  controller and the overlay mixer. Budget **1,500–3,000 ALMs**. Palette + line buffers ~4–8 M10K.
- **Two 128 KB frame buffers** = 2,097,152 bits = **205 M10K blocks if on-chip. Impossible — there
  are 34 free.** They must live in **SDRAM** (S32X_MiSTer already keeps them there; confirm).
- **256 KB SH-2 SDRAM** (the 32X's own work RAM): also external.
- **SH-2 boot ROMs** (2 × 2 KB) and the 32X's small vector/comm RAM: a handful of M10K or MLAB.
- **PWM**: small logic + two FIFOs (a few M10K or MLAB).
- **32X-on-cart-bus glue**: the register decode, the 68000-side FIFO/DREQ DMA, ROM banking, the
  H-int line counter, the "adapter enable/cart mode" logic. ~500–1,000 ALMs.
- **Rough total: 12,000–17,000 ALMs and 20–40 M10K** (frame buffers and SH-2 RAM excluded because
  they go to SDRAM).

### 3.3 The arithmetic

- **With NukedMD:** 35,405 + ~14,500 ≈ **50,000 ALMs > 41,910. Does not fit.** Even before M10K.
  This is the numerical proof behind the decision in §2.
- **With fpgagen MD:** the original srg320 MegaCD core's MD side is a behavioural 68000 (fx68k),
  behavioural VDP, T80 Z80 and jt12 FM — historically **~6,000–8,000 ALMs** for the MD block vs
  NukedMD's 13,392, i.e. it **frees ~5,500–7,500 ALMs**, and its VRAM/regs are similar. The
  MegaCD block stays at ~7,800 / 293 M10K.
- **Then strip the optional extras** (all reclaimable without touching hardware behaviour):
  two Game Genie engines **2,320 ALMs**, Hq2x **571 ALMs + 14 M10K**, TMSS ROM out of LUTs
  **511 ALMs** (or into 1–2 M10K), video_freak **325**, lightgun **144**, Saturn keyboard **94 + 1
  M10K**, mcd_cart EEPROM models **138**, and consider dropping the scandoubler path if the scaler
  is always used. **≈ 4,000 ALMs + ~15 M10K back.**
- **Resulting budget for the 32X:** roughly (41,910 − 35,405) + 6,500 (fpgagen saving) + 4,000
  (extras) ≈ **17,000 ALMs nominal**, against a 12,000–17,000 ALM 32X. **It fits on paper, with
  little margin, and only if the fitter is happy at ~90 % — expect a fight for the last 10 %.**
- **M10K:** 34 free + ~15 reclaimed ≈ **50 blocks for the 32X's on-chip needs** (caches, palette,
  FIFOs, boot ROM). Enough only if frame buffers and SH-2 RAM are in SDRAM and the SH-2 caches are
  either small or also externalised/disabled. **The Word RAM (256 blocks) and work RAM (64) are the
  two big fixed costs; neither can move without hurting the MCD/MD timing.**

**Bottom line:** feasible, tight, and entirely dependent on (a) fpgagen MD, (b) every 32X memory
bigger than a few kbit living in SDRAM, (c) removing the extras. Phase 0 exists to replace the
estimates in §3.2 with measurements before anyone writes glue.

## 4. Architecture of the combined core

### 4.1 Bus topology (mirror the hardware)
```
                 +-------------------------------------------------------------+
                 |  Mega Drive (fpgagen): 68000, VDP, Z80, FM/PSG, IOC, arbiter |
                 +-----------+---------------------------+---------------------+
                             | cartridge bus (/CE0, /CART, A[23:1], D[15:0], /AS, /DTACK...)
                     +-------+--------+
                     |      32X       |  regs $A15100-3F, FB window $840000/$860000,
                     | 2x SH-2, VDP,  |  SH-2 vectors; passes ROM through to the game cart
                     | PWM, FB ctrl   |  (ROM banking regs), adds cart-access wait states
                     +-------+--------+
                             | (cart ROM behind the 32X) -> SDRAM port: cart
                             | expansion port (/ASEL, /ROM, /RAS2, /FDC, /DTACK, ...)
                     +-------+--------+
                     |    Mega CD     |  $400000 window, $A12000 gate array
                     | sub-68K, ASIC, |  BIOS/PRG/Word/PCM RAM -> SDRAM ports
                     | CDC, PCM, CDD  |
                     +----------------+
```
- The MD is the master. The 32X sits **on the cart bus**, so in RTL it is instantiated where
  `mcd_cart` / the cartridge decode is today, and the game ROM port of SDRAM is reached *through*
  the 32X block (it owns ROM banking and the 32X-mode remap). The MCD stays exactly where it is on
  the expansion connector (`exp_*` signals). **The two peripherals never talk to each other
  directly** — the CD32X titles move data via the 68000 and Word RAM, which is why the stack works
  on real hardware and why the merge is "two independent grafts onto one MD", not a three-way bus.
- **Address-decode collisions to check first:** the 32X's $A15100 register window vs the MCD's
  $A12000 gate-array window (no overlap — good); the 32X frame-buffer window $840000-$87FFFF vs the
  MCD's $400000-$7FFFFF (no overlap); the 32X "ROM mirror" at $880000/$900000 (32X banked ROM) vs
  nothing MCD (fine). The cartridge /CE0 region $000000-$3FFFFF is where the 32X does its remap;
  the MCD BIOS also lives at $000000 when no cart is present — **this is the one real conflict**:
  with a 32X present the MD's $000000 sees the 32X's vector table / adapter first, not the MCD BIOS.
  On real hardware the CD32X titles are booted **from the 32X cart side** (the 32X cart is
  inserted; the MCD provides data). Define the boot precedence explicitly in the core: cart present →
  32X cart mode; no cart → MCD BIOS at $000000 (exactly as this project's `rom_cart_mode` does).

### 4.2 Memory map onto SDRAM (the second hardest problem)
This project's `rtl/sdram.sv` has **5 ports with fixed priority**: cart ROM, MCD BIOS, PRG-RAM,
PCM RAM, load/save. The 32X needs at minimum: **two frame buffers (2×128 KB)**, **256 KB SH-2 work
RAM**, and its **ROM path** (which can share the cart port). That is +3 ports and, critically, **a lot
of bandwidth**: the 32X VDP reads a frame buffer at up to 320×224×15-bit per frame while the SH-2s
write the other one, on top of the MD cart fetches, the MCD BIOS/PRG/PCM traffic and CD data.
- Do a **bandwidth model in Phase 0** (bytes/frame per port, worst case = CD32X FMV: SH-2s writing
  a frame buffer from Word RAM while the VDP reads the other, PCM playing, PRG-RAM busy). The DE10
  SDRAM (single 16-bit, ~100–130 MHz) is probably enough with a good scheduler, but the frame-buffer
  read must be **line-buffered** (prefetch a scanline into ~1–2 M10K) so it never stalls the VDP.
- If SDRAM cannot carry it all, the **HPS DDR3** (via `ddram`) is the escape hatch for the frame
  buffers — higher latency, so only with the line-buffer approach. The MegaCD PCM RAM already moved
  to SDRAM in this project (`rtl/pcm_mem.sv`, write FIFO + read-holds-DTACK); reuse that pattern.
- **Do not put any 32X memory in M10K "for now"** — §3.3 shows there is nowhere for it to go later.

### 4.3 Clocks and enables
- MD master: 53.693175 MHz NTSC / 53.203423 PAL (`clk_sys`); 68000 = /7; the whole MD side is
  enable-stepped from it (fpgagen style).
- MCD: its own **50 MHz** crystal in hardware; this project derives a **50 MHz enable** from
  `clk_sys` with `CEGen` (`mcd_cegen`) so the sub-68000/PCM/CDC run at the true 12.5 MHz instead of
  53.69/4 = 13.42 MHz (the original core was 7.4 % fast). Keep this; it is region-independent
  (the console clock changes with region, the CD unit's does not).
- 32X: SH-2 at **23.011 MHz = 3 × VCLK** in hardware, so it is **derived from the MD master clock**,
  not independent — implement as an enable from `clk_sys` at exactly 3× the 68000 rate (53.69/7×3 =
  23.011 MHz NTSC; PAL gives 22.80 MHz, which is also what real PAL 32Xs do). The 32X VDP is
  genlocked to the MD VDP (same H/V), so drive it from the MD VDP's timing, not a separate counter.
- The design already runs a **107 MHz `clk_ram`** domain (SDRAM + the NukedMD sampling clock) that is
  timing-tight (see this project's STATS.md / HANDOFF for the sta_paths work). With fpgagen the
  107 MHz sampling requirement goes away; the SDRAM controller still wants ~100+ MHz. Expect SH-2 →
  SDRAM and SH-2 cache paths to be the new critical paths.

### 4.4 Reset topology (get this right on day one — see §8.1)
One shared reset. **Cold reset** (`loading` = BIOS/ROM download, backup-RAM clear) resets everything
and clears work RAM. **Warm reset** (front button / OSD Reset) must reset the MD *and both
peripherals together*, hold the 68000 until the peripherals' ROM/vector paths are live, and **preserve
work RAM** (X-Men reset-to-continue on the MD; the Mega CD BIOS uses preserved RAM to tell warm from
cold). For the 32X add: the SH-2s must be held in reset until the 32X adapter is up, and the "32X
cart mode / adapter enable" latch (the MD-side register that says whether the 32X is active) must
survive or be re-established correctly — 32X games set it at boot.

### 4.5 Video
The 32X VDP's output is **composited over** the MD VDP's output with per-pixel priority (the /YS
mechanism — background pixels of the MD show through where the 32X pixel is "transparent" or
low-priority, and vice-versa per the 32X's priority bit). S32X_MiSTer already implements this mixer;
lift it, and make sure it sits *before* `video_cond`/`cofi`/the scaler so the composite goes through
one video path. H32/H40 and interlace must be respected on both sides.

### 4.6 Audio
Three sources: MD FM+PSG, MCD PCM+CDDA (mixed in *before* the Genesis LPF in this project —
"CD Audio: Filtered", `rtl/audio_cond.sv`), and **32X PWM** (which on hardware enters the MD's
audio mix through the cartridge port's audio-in pins — i.e. it is mixed **at the MD**, like the MCD
audio). Extend `audio_cond` to a three-way mix with per-source enables; keep the existing LPF/IIR
chain (they are ~30 DSPs today; budget is fine).

### 4.7 Main (HPS) side
Three media types at once: a cart image (32X or MD), a disc image, and optional per-game files.
Reuse `support/megacd` (disc, CDD, save) and `support/s32x` (32X ROM load, the adapter flags), and
define the OSD: Insert Cartridge (MD/32X, auto-detect by header "SEGA 32X"), Insert Disk, Remove
Cartridge & Reset, Eject Disc, Reset, Reset & Eject. Carry over every Main lesson in §8.3.

## 5. Compromises — stated up front so nobody is surprised
1. **fpgagen MD, not NukedMD** (§2, §3). Accept failing the verificator's cycle-exact MD tests.
2. **All large 32X memories in SDRAM** (frame buffers, SH-2 RAM), line-buffered for the VDP.
   Risk: subtle timing differences in frame-buffer access vs the real SDRAM-on-cart.
3. **Strip the extras**: both Game Genie engines, Hq2x, video_freak, lightgun, Saturn keyboard,
   Pier Solar EEPROM models, TMSS-in-LUT (or keep TMSS but in M10K). Possibly drop SNAC.
4. **SH-2 caches**: if the S32X SH-2 keeps a 4 KB cache in M10K each (~8 blocks total) that is
   affordable; if it needs more, consider a smaller/direct-mapped cache — timing-visible but
   tolerable.
5. **One video output path**: no separate 32X "raw" output mode.
6. **Accept a slower fitter/timing loop**: at 90 %+ utilisation every build is 35–45 min and seeds
   matter (this project shipped several "seed N" builds).

## 6. Roadmap — phases with GO/NO-GO gates

### Phase 0 — Feasibility by measurement (1–3 days, no glue written)
1. Clone `srg320/S32X_MiSTer`. Build it as-is for the DE10-Nano; record ALMs/M10K/DSP per entity
   (the same `Fitter Resource Utilization by Entity` extraction used for §3; the parser is in the
   scratchpad as `parse_entity.py`). Separate the 32X block from its fpgagen MD.
2. Build `MegaCD_MiSTer-master_ORIG` (srg320 upstream, fpgagen) as-is; record per-entity numbers.
   Separate the MCD block from its MD.
3. Sum: fpgagen MD (once) + MCD block + 32X block + framework − extras. Compare with 41,910 ALMs /
   553 M10K. **GO if ≤ ~90 % ALMs and ≤ ~92 % M10K with all frame buffers/SH-2 RAM external;
   otherwise stop and redesign (§7).**
4. SDRAM bandwidth model for the CD32X worst case (spreadsheet: bytes/frame per port). **GO if
   < ~70 % of the SDRAM's sustained bandwidth with the line-buffer scheme.**

### Phase 1 — Base core (1 week)
Start from `MegaCD_MiSTer-master_ORIG` (fpgagen + MCD). Bring it up on hardware exactly as it is:
BIOS boot, a CD game, a cart. Port over from this project only the things that are bug fixes or
neutral improvements, **not** NukedMD: the region-from-BIOS fix (`$1F0` sniffed on the BIOS
download, not the cart), the cartridge-slot/`rom_cart_mode` handling, the CEGen 50 MHz enable, the
PCM-RAM-in-SDRAM, the CDC `SECTOR_ACTIVE`/frame-timer fixes, the ASIC INT2 acknowledge fix, the
reset topology (§8.1), and the Main patches (§8.3). Re-run the verificator to get the fpgagen
baseline (expect < 11/12). Strip the extras from §5 now, while the design is small, and measure.

### Phase 2 — MD + 32X (2–4 weeks)
Graft the 32X block from S32X onto Phase 1's cart bus (`mcd_cart` becomes "cart-or-32X"; ROM port
via the 32X). Add the SDRAM ports (frame buffers + SH-2 RAM) with the line-buffered VDP read. Add the
23 MHz enable and the video overlay mixer. Milestones: 32X boot ROM → Virtua Racing Deluxe title →
Doom 32X gameplay → Knuckles Chaotix (heavy frame-buffer use). MCD block still instantiated but idle
(no disc) — **this is where fit/timing is first proven with everything present.**

### Phase 3 — MD + MCD with the 32X present (1–2 weeks)
Boot the Mega CD BIOS and a CD game with the 32X block instantiated and idle. Check the $000000 boot
precedence (§4.1), the shared reset with three units (§4.4), and that MCD PCM/CDDA and 32X PWM coexist
in the mix. Verificator again.

### Phase 4 — CD32X (2–3 weeks)
Night Trap 32X / Corpse Killer 32X. These stream from the MCD into Word RAM and blit to the 32X frame
buffer via the SH-2s — the SDRAM scheduler's worst case. Expect to tune port priorities and the
frame-buffer prefetch here. Acceptance: all six CD32X titles boot and play.

### Phase 5 — Hardening and accuracy (ongoing)
Timing closure at the chosen seed, long soak (this project found a mid-game crash only after hours),
32X test ROMs (SH-2 timing, PWM), the verificator for the MD/MCD side, and the `hpsmem.py` telemetry
technique for live state when screenshots are not enough. Then release.

## 7. Risks and what to do about them
| Risk | Likelihood | Mitigation |
|---|---|---|
| **Doesn't fit** (ALM or M10K) even with fpgagen + extras stripped | Medium | Phase 0 measures before any glue. Fallbacks in order: drop the scandoubler path; move TMSS/boot ROMs to SDRAM; shrink SH-2 caches; put Z80 RAM/backup RAM in SDRAM; last resort: Word RAM to SDRAM with a cache (timing-visible to MCD games — avoid). |
| **SDRAM bandwidth** for CD32X | Medium | Bandwidth model in Phase 0; line-buffer the frame-buffer read; give the 32X VDP read the top priority after the MD cart fetch; consider DDR3 for the frame buffers if needed. |
| **Timing closure** with SH-2s in a 90 %-full device | High | Keep the 32X on `clk_sys` enables (not a separate clock); register SDRAM boundaries; expect seed sweeps. This project's `tools/sta_paths*.tcl` find the failing paths fast. |
| **32X cart-bus timing** (wait states, DREQ FIFO, H-int) on fpgagen's cart cycle | Medium | S32X already runs on fpgagen — lift its glue verbatim first, then fix against test ROMs. |
| **Boot precedence / $000000 conflict** between 32X vectors and MCD BIOS | Low–Medium | Define it in RTL from `rom_cart_mode` + "32X cart detected" (header check in Main); test all four tiers' boots explicitly. |
| **Reset topology with three units** | Medium (it cost days here) | Apply §8.1 from day one; test warm reset in all four tiers before anything else. |
| **Main complexity** (cart + disc + 32X flags + saves) | Medium | Reuse both support dirs; write the media state machine down before coding; keep the per-game-save semantics but never let a save/BIOS load reset the core on a disc *insert* (§8.3). |
| **fpgagen accuracy regressions** vs the NukedMD release | Certain, accepted | Ship the NukedMD MD+MCD core separately as the accurate one. |

## 8. Lessons from the NukedMD-MegaCD project to carry forward (hard-won; read before designing)

### 8.1 Reset — the shared line, and how the CD side must be treated
- The front reset button is a **warm** reset. On the FC1004 die the `WRES` input produces a **fixed
  ~17 µs RESET+HALT pulse** to the 68000 regardless of how long the button is held; `SRES` (power-on)
  holds everything for its duration. fpgagen models this more loosely, but the *semantics* to keep are:
  warm reset preserves work RAM and does not clear anything; cold reset (download) clears.
- **The peripheral blocks must reset together with the console** (shared line) — the Mega CD BIOS
  re-detects the disc because its CDC re-syncs with the drive. Decoupling the CD block from the warm
  reset "fixed" a freeze but broke disc detection (build 65 here). Wrong lever.
- **Hold the 68000 until the peripheral is ready.** With the CD block held ~9.5 ms and the 68000
  released after 17 µs, the CPU fetched from a parked BIOS-ROM path and froze. Fix: drive
  `md_board.ext_vres` (68000 RESET+HALT only, not the VDP) for the whole warm-reset window so the
  CPU is released together with the block (build 66). For the 32X the same applies to the SH-2s
  and the adapter.
- **The disc stays in the tray across a warm reset**, the BIOS re-runs and boots it (Mega CD is
  different from the MD here: an MD cart restarts its game; the Mega CD goes back through the BIOS).
- **Main's CDD gets a reset request (`data_in[0]==0xFF`) once per `MCD_RST_N` falling edge**, which
  is pulsed on *every 68000 RESET instruction* the BIOS executes (ASIC `ERES_N`). That is normal
  boot traffic — a cold boot produces it too. Do not try to suppress it; `cdd.Reset()` keeps the disc
  loaded. (An attempt to short-circuit it froze the BIOS.)

### 8.2 Fit and timing tricks that bought this project its last 10 %
- PCM wave RAM (64 KB) into SDRAM with a write FIFO and a read that holds the sub-CPU's /DTACK
  (`rtl/pcm_mem.sv`) — saved ~64 M10K.
- VDP VRAM banks writing full 256-bit rows so M10K uses ×40 mode: 7 blocks per bank instead of 13.
- Telemetry (`MCD_TELEMETRY`) had to be compiled out to fit; ~1,500 ALMs. Design telemetry so it can
  be dropped by a single macro from day one.
- `quartus_sta -t tools/sta_paths.tcl` to find the true 107 MHz offenders; placement, not logic, was
  usually the cause; seed sweeps were routine.
- Quartus 17.0 on this machine: intermittent `quartus_fit` access violations early in the fitter
  (rerun works), and **wedged `quartus_*` zombies that survive `taskkill /F`** — kill them with
  PowerShell `Get-CimInstance Win32_Process | Invoke-CimMethod Terminate` and delete `db/` +
  `incremental_db/` before rerunning. Check for a fresh `.rbf` timestamp and Fitter/Assembler/STA
  "successful" lines — the pre-flow `quartus_sh` prints "successful" too and is not a flow result.

### 8.3 Main (HPS) behaviour that matters
- **A BIOS or cart download is a full cold reset in the core** (`bios_download|cart_download → loading
  → md_reset`, RAM cleared). So inserting a disc must NOT reload the BIOS — Main auto-loads
  `<home>/boot.rom` at core start; a disc cannot change the console's BIOS. Inserting a disc must be
  a faithful tray-close (`cdd.Unload → CD_STAT_OPEN → Load → CD_STAT_STOP`), no `status[0]` pulse.
  Per-game `cd_bios.rom`/`cart.rom` are genuine hardware swaps and may reset — only if the file exists
  (`user_io_file_tx` opens the file before touching the download strobe).
- **Save mounting does not reset the core**: `mcd_mount_save` is an SD-image mount on ioctl index 5
  (not a ROM index) and `bk_loading` is driven only by the OSD Reload/Save/autosave status bits.
- Real Mega CD backup RAM is the console's, shared by all games; MiSTer's per-game save file is a
  convenience that only makes sense together with "different game ⇒ swap save". Keep it, but never
  couple it to a machine reset.
- `MiSTer`'s stdout is block-buffered when redirected — add `setvbuf(stdout, NULL, _IOLBF, 0)` (done
  in the fork) or you will chase phantom "the key didn't arrive" bugs.
- The OSD is composited after the scaler and **never appears in a screenshot**; drive it blind by
  index (`tools/mister/osd.py`), bottom-anchored items are invariant to hidden rows.
- **MGL `<rbf>` is a prefix**; two rbfs sharing it → Main loads the last in sort order. Name test
  builds uniquely (`MegaCD_TEST_b66_...`) and give each its own MGL.
- Exactly **one** `uinput_kbd.py` daemon (it keeps a pidfile); verify with
  `ls /sys/class/input/event*/device/name | grep -c 'MiSTer virtual keyboard'`, not `ps`.
- Build Main in WSL (Ubuntu, ARM 10.2 toolchain, `wslbuild.sh`); `touch` the edited sources first —
  /mnt/c mtime skew makes `make` reuse stale objects. `/media/fat` is FAT: you cannot overwrite the
  running `MiSTer` binary — stage to `MiSTer.new`, `killall MiSTer`, `cp`, relaunch with
  `setsid /media/fat/MiSTer` (inittab does not respawn it).

### 8.4 Expansion-port facts that transfer (MCD side)
- The MCD answers inside the MD's fixed bus cycle (the FC1004 auto-DTACKs every A23=0 access one
  VCLK after /AS — on NukedMD; fpgagen's cart cycle is looser but the MCD block was written for it).
- The ASIC's `/VPA`-terminated interrupt acknowledge (E-clock synchronised autovector, 13–22 sub
  clocks) is faithful and is why mcd-verificator IRQ 0A is marginal; the one avoidable latency is the
  `MC68K` wrapper's MCLK output register on the sub-CPU control strobes (~93 ns) — make the strobes
  combinational, keep wide buses registered (deferred fix, documented in this project's HANDOFF).
- REF on the FC1004 is bus-derived and unrouted; there is no die "refresh stall" to model (jgenesis's
  2/172 stall is a band-aid for a behavioural CPU — irrelevant to fpgagen too? **No**: fpgagen *is*
  behavioural, so it may need the documented ~2/128 work-DRAM refresh stall to pass VAR/IRQ09 — test
  in Phase 1, do not assume).

## 9. Open questions to answer in Phase 0
1. Exact ALM/M10K/DSP of S32X's SH-2 (×2), VDP, PWM and glue. (Measure.)
2. Where S32X keeps its frame buffers and SH-2 RAM today (SDRAM? DDR3?) and how it arbitrates.
3. Whether S32X's fpgagen MD and MegaCD_ORIG's fpgagen MD are the same revision (they should be —
   same author — but diff them; any drift is merge work).
4. The CD32X titles' actual SDRAM demand (measure with the bandwidth model, then on hardware).
5. Whether fpgagen needs a refresh stall to pass VAR/IRQ09 (§8.4).
6. Cart-header detection for "this is a 32X cart" in Main (the "SEGA 32X" / "MARS" ID) and how the
   adapter-enable latch is set on real hardware vs in S32X.

## 10. Suggested first two weeks
- Day 1–2: clone S32X_MiSTer; build both srg320 cores unmodified; extract per-entity resource tables
  (use `parse_entity.py`); write the §3.3 sum with real numbers; SDRAM bandwidth sheet. **GO/NO-GO.**
- Day 3–5: Phase 1 base from `MegaCD_MiSTer-master_ORIG`; strip §5 extras; port the neutral fixes and
  the reset topology; verificator baseline; measure again.
- Week 2: start Phase 2 — instantiate the 32X block idle (no bus connection) just to prove fit and
  timing with everything present. Only then wire the cart bus.

---
*Reference numbers: this project's build-65 fit report is saved as `scratchpad/b65.fit.rpt` with a
parsed `entity.tsv`; the NukedMD-MegaCD `HANDOFF.md`/`STATS.md` hold the full bring-up history, the
verificator verdict (11/12 NTSC; PAL's VAR/REG8030/IRQ09 are fixed-NTSC constants in the ROM) and the
IRQ 0A root-cause analysis.*

---

# SESSION LOG — 2026-09-09 (Phase 0 in progress)

## Done
- Private repo created: github.com/retrorepair/MiSTer_Megadrive_MegaCD_32x (local `main`, identity retrorepair).
- Vendored (git dirs stripped, `phase0/UPSTREAM_VERSIONS.txt`): `S32X_MiSTer_upstream/` (srg320 S32X_MiSTer dae3f17), `32X/` (srg320/32X), `SH/` (srg320/SH; `SH7604` = the SH-2), `phase0/MegaCD_ORIG/` (pristine srg320 MegaCD_MiSTer copy).
- Tooling: `tools/build.sh` (detached Quartus 17.0 compile — the Bash tool kills anything after 10 min, even backgrounded), `tools/py.sh` (Python via WSL; no native Python here), `tools/parse_entity.py` (fit-report entity table → tree/TSV).
- Both unmodified cores are being compiled for the per-entity resource tables (`phase0/build_*.log`).
- `phase0/BANDWIDTH.md`: the SDRAM bandwidth model. Result: frame buffers on SDRAM = ~90 % (FAIL); frame buffers + SH-2 RAM on DDR3, MD/MCD on SDRAM = ~34 % SDRAM (PASS).

## Findings that change the roadmap (answers to §9)
1. **Q3 — the two fpgagen MDs are NOT the same revision.** S32X has a newer `rtl/GEN/gen.sv` (+`ba.sv` bus arbiter, `vdp.sv`/`vdp_pkg.sv`, `rtl/CART/cart.sv`); MegaCD_ORIG has the older `gen.sv` + `vdp.vhd`. gen.sv diff ≈ 2,000 lines. The **S32X gen is a superset**: it exposes the 32X-side signals (YS_N, EDCLK, CAS0_N, CAS2_N, LWR/UWR) *and* the expansion-port signals the MCD needs (ASEL_N, RAS2_N, ROM_N, FDC_N, CART_N, DISK_N, VCLK_CE). The old gen lacks YS_N/EDCLK/CAS0/CAS2. **Decision proposed: MD RTL = S32X's `rtl/GEN` + `rtl/CART`; top level + framework + MCD plumbing = MegaCD_ORIG's `MegaCD.sv`/`sys/` (the newer MiSTer framework: `emu_ports.vh`, `hps_io.sv`; S32X's `sys/` is the older one).** The 32X glue then stays exactly as srg320 validated it.
2. **Q2 — where S32X keeps its memories:** BOTH 128 KB frame buffers are in M10K (`spram` ×4 in S32X.sv, ~205 blocks) and the SH-2 256 KB work RAM is in **DDR3** (`rtl/ddram.sv`, 16-byte line cache, 4 channels, one request port) with an OSD option for SDRAM. So the frame buffers must move; plan = DDR3 with a per-line burst prefetch into a 1-M10K line buffer (details in BANDWIDTH.md). The 32X VDP already separates display (`FB_DISP_*`) and draw (`FB_DRAW_*`) streams internally.
3. **Q6 / boot precedence:** the 32X's 68K-side vector overlay is decoded on **/CE0** (`32X/IF.sv`: `CCE0_N = ... MD_BIOS_SEL | CE0_N`), and gen decodes /CE0 as $000000-3FFFFF only when CART_N=0. With no cart, $000000 → /ROM → MCD BIOS, the overlay lands harmlessly at $400000. So the "$000000 conflict" in §4.1 does not exist if **CART_N is driven from cart-present** (S32X hardwires `.CART_N(0)`; MegaCD_ORIG drives it from its CART module — keep the latter). 32X registers ($A15100) and the 32X ROM window ($880000) are address-decoded, so CD32X discs can enable the adapter (ADEN) without a cart, as on hardware. Main marks 32X ROMs via `ioctl_index[7:6]` (`s32x_rom`).
4. **SH-2 clock:** S32X steps the SH-2s on `CE_R = clk_sys/2` = **26.85 MHz, 17 % faster than the real 23.01 MHz**. The exact 3-of-7 enable (53.69×3/7) is present but commented out in `32X/32X.sv`. For accuracy the 3/7 pattern should be restored (test for regressions — srg320 may have had a reason).
5. **SH-2 cache:** 4-way, 64 sets × 16 B; data in 4 × (1024×8) M10K, tags 4 × (64×20) and LRU 2 × (64×6) which fit MLAB. ~4–10 M10K per CPU. The 2-way mode bit (CCR.TW) is implemented.
6. **SH-2 MULT** does a signed and an unsigned 32×32 multiply side by side (DSP blocks; DSP is not a constraint).
7. **Q5 (fpgagen refresh stall):** untested; Phase 1 item.
8. **NukedMD-MegaCD MCD fixes are small, portable patches** (whitespace-ignored): `ASIC.vhd` 209 lines, `CDC.vhd` 153, `PCM.vhd` 52, `MCD.vhd` 92 (adds `pcm_mem.sv` PCM-RAM-in-SDRAM ports, `EN50` 50 MHz enable, and Nuked-sub-CPU-specific `MCLK`/`S68K_CLK` which are dropped if the sub-CPU stays fx68k). `MC68K.vhd` (226) is the Nuked wrapper — not ported unless the Nuked sub-CPU is chosen. Every fix is commented with the mcd-verificator test it satisfies.
9. **SDRAM controller** (`sdram.sv`, both cores): 3 ports, single word per request, ~7 clocks each at 107.39 MHz.
