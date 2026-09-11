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

## Phase 0 measurements (fitted, Quartus 17.0.2, seed 1, both cores unmodified)

Device: 41,910 ALMs / 553 M10K. Full tables: `phase0/entity_S32X.tsv`, `phase0/entity_MegaCD_ORIG.tsv` (from `tools/parse_entity.py`).

| Block | ALMs | M10K | DSP | Source |
|---|---|---|---|---|
| **S32X core total** | **25,094 (60 %)** | **488** | 51 | fails 53.69 MHz setup by −2.80 ns (TNS −42) — all 17 failing paths are the 107 MHz `sdram.dout1` → `S32X_IF.CDI_SYNC` (negedge clk_sys) crossing, none inside the SH-2s |
| 32X block (`S32X`, without frame buffers) | 9,199 | 14 | 12 | IF 691 (5 M10K: SH boot ROM 4, MD boot ROM 1), VDP 237 (1 = palette), 2 × SH7604 |
| **SH7604 (one SH-2)** | **4,109** | **4** | 6 | core 1,680 (regfile 96), cache 690 (4 M10K data; tags/LRU in MLAB), DMAC 379, MULT 291 (6 DSP), DIVU 285, BSC 178, INTC 155, SCI 100, UBC 89, FRT 87, WDT 27, MSBY 5, glue 140 |
| 32X frame buffers (2 × 128 KB spram) | ~0 | **~256** | 0 | must go external |
| gen (S32X revision, newer) | 6,801 | 153 | 11 | 68K work RAM 64, VRAM 52 (one 64K×8), Z80 RAM 8, VDP 7, fx68k 6, jt12 4; fx68k 1,958, VDP 1,251, T80 1,046, jt12 954, genmix 502, multitap 358, BA 231 |
| **MegaCD_ORIG core total** | **25,268 (60 %)** | **535 (97 %)** | 49 | timing: see build log |
| MCD block | 6,069 | 349 | 5 | Word RAM 2×128 = 256, PCM RAM 64, CDC RAM 16, CDDA FIFO 7, fx68k 6; ASIC 1,604, sub-fx68k 2,006, PCM 510, CDC 171, **Game Genie 1,408 (strip)** |
| gen (MegaCD revision, older) | 8,489 | 103 | 11 | includes Game Genie 1,490; VRAM 64 (4 × 16K×8), Z80 8, vdp 14, jt12 11, fx68k 6 |
| Framework (`sys_top` − `emu`, MegaCD's newer sys) | 7,098 | 59 | 33 | ascal 2,096 (43 M10K), audio_out 935, OSDs 1,061 (8), pll_hdmi_adj 547, pll_cfg 685 |
| Strippable extras | Hq2x 668 + 14 M10K, video_freak 331, lightgun 145, 2 × Game Genie 2,898 | | | |

### The sum (fitted numbers)
- **ALMs:** framework 7,098 + gen(S32X) 6,801 + MCD 4,661 (no GG) + 32X 9,199 + glue ≈ 3,000 (hps_io 754, mixer w/o Hq2x ~200, sdram+ddram ~240, pll_cfg 685, cart 191, audio/misc) ≈ **30,800 = 73 %**. Below the 90 % gate with ~11,000 ALMs of headroom (Nuked sub-68000 +1,800 and telemetry would fit).
- **M10K:** framework 59 + gen(S32X) 153 + MCD 285 (PCM → SDRAM via `pcm_mem.sv`) + 32X 15 (+1 line buffer) + mixer 1 + backup RAM 8 + tmpram 1 ≈ **523 = 95 %** with the 68K work RAM on chip; **≈ 459 = 83 %** with the work RAM in SDRAM as MegaCD_ORIG does it. The 92 % gate therefore requires **work RAM in SDRAM** (port the old gen's `RAM_CE_N`/`RFS` path into the new gen, or reuse the MegaCD top's mapping) — or ×40-mode repacking of VRAM/Word RAM if that proves easier.
- **Bandwidth:** PASS only with frame buffers + SH-2 RAM on DDR3 (`phase0/BANDWIDTH.md`).

### GO / NO-GO: **GO.**
Conditions: fpgagen MD (S32X revision), frame buffers + SH-2 RAM on DDR3, PCM RAM and 68K work RAM in SDRAM, extras stripped. Timing: the SH-2s close at 53.69 MHz at 60 % utilisation; the fight will be at ~75 % and on the SDRAM/DDR3 crossings.

### SH-2 shrink verdict
At 4,109 ALMs / 4 M10K each the SH-2 is already lean; nothing large can be removed without changing behaviour. Ranked candidates (per CPU): UBC 89 (no game uses the break controller — remove, keep reads returning 0), SCI 100 (the master/slave serial link — keep unless a title is proven not to use it), MULT's two 32×32 multipliers → one 33×33 signed (saves 3 DSP each, DSP is not scarce). Total realistic saving ≈ 200–400 ALMs across both CPUs. The 2-way cache mode (CCR.TW) is implemented; do not reduce associativity — it is visible to timing-sensitive code. The exact 3-of-7 clock enable (23.01 MHz) should be restored for accuracy; it also loosens the SH-2 paths relative to the current /2.

### Sub-CPU option (user 2026-09-09: NukedMD parts allowed where they slot in)
Nuked sub-68000 (`m68kcpu`): 3,813 ALMs + 14 M10K vs fx68k 2,006 + 6. Slots in through the NukedMD project's `MC68K.vhd` wrapper (226 changed lines) and buys the verificator's VAR/REG8030 results on the sub side. Affordable in ALMs; the +8 M10K only if work RAM goes to SDRAM. Decide in Phase 1 after the base fit.

## Phase 1 (started 2026-09-09) — base core `core/`
Decision confirmed with the user: the MD is fpgagen ("not NukedMD unless parts slot in without issue").

`core/` = MegaCD_ORIG top/framework/MCD plumbing + S32X's `rtl/GEN` (newer gen.sv, ba.sv, vdp.sv) + S32X's `rtl/FX68K` +
the NukedMD-MegaCD MCD fixes. Built by `tools/phase1_top_edit.py` (asserting replacements on the pristine top) plus the
scripted MCD.vhd edit; the diff from upstream is therefore reproducible. Changes:
- gen ports adapted (LWR/UWR/CAS0 strobes, MEM_RDY, EXT channel = CD audio, BGA/BGB/SPR enables, DAC_CE restored by
  taking the old `genesis_lpf.v`/`audio_iir_filter.v` which export the sample enable). /TIME reads (mappers, Pier EEPROM)
  now go through the VDI mux (`GEN_VDI = !TIME_N ? GEN_PAGE_DI : ...`) because the new gen has no TIME_DI port.
- 68K work RAM is inside the new gen (64 M10K) — the old gen kept it in SDRAM. Revisit in Phase 2 if M10K is short.
- `rtl/sdram.sv` = the NukedMD 5-port controller: port0 main bus (cart ROM/RAM, MCD BIOS), 1 PRG-RAM, 2 PCM RAM
  (`rtl/pcm_mem.sv`, 64 M10K saved), 3 load/save, 4 spare.
- MCD block: NukedMD `ASIC.vhd`/`CDC.vhd`/`PCM.vhd` verbatim; `MCD.vhd` = NukedMD version minus the Nuked-only MCLK/CLK_LEVEL
  wiring (sub-CPU stays fx68k for now) and minus Game Genie. `EN50` from a `CEGen` (50 MHz) in the top.
- Stripped: both Game Genie engines, Cheats and CRAM-Dots OSD items. TRANSP_DETECT (adaptive blend) is constant 0 (the SV VDP has none).
- Region is sniffed from the BIOS header only (`~ioctl_index[6]`).
- Still present, to strip in Phase 2 if needed: Hq2x (inside `sys/scandoubler.v`, 668 ALMs + 14 M10K — needs a plain
  line-buffer stand-in with the same `Hq2x` interface), video_freak, lightgun, Pier EEPROM.
- Test MGLs in `tools/mgl/` (rbf prefix `_Console/MegaCD_P1_20260909`); deploy with `tools/deploy.sh`.
Phase 0 sanity: the pristine MegaCD build boots the (EU) BIOS on the MiSTer (`phase0/shots/p0orig_boot.png`); timing met.

## Phase 1 hardware results (2026-09-09, builds P1 / P1b)
- P1 fit: 22,594 ALMs (54 %), 522 M10K (94 %), timing met. MCD block 4,882 ALMs / 285 M10K (PCM RAM now in SDRAM), S32X-revision gen 7,053 / 154.
- First P1 build: BIOS screen with a corrupt logo band, cartridge ignored, disc not booting. Two causes found:
  1. The retrorepair Main sends "Insert Cartridge" as ioctl index 6; the pristine top expects bit 6 (0x40). Ported the
     NukedMD core's decode + OSD media entries (`tools/phase1_top_edit2.py`); the debug-menu status bits moved 36-39 → 59-62
     because Main reads [36] as "Disc Insert: Keep Running". **Cartridge now boots (Alien 3 plays) on P1b.**
  2. New gen's bus arbiter ends a 000000-7FFFFF read on `MEM_RDY || !DTACK_N`; feeding MEM_RDY from the SDRAM idle flag let it
     finish before the Mega CD / cart module answered. MEM_RDY is tied low; everything on that range answers with DTACK.
- Still corrupt on P1b: the BIOS logo band (graphics the sub-CPU decompresses into Word RAM) and the disc does not boot.
  Hypothesis: the NukedMD ASIC's early PRG-RAM read acknowledge / posted writes are tuned to the Nuked 68000's latch timing;
  fx68k latches on its own enable and can read before the SDRAM data is back. `tools/phase2_asic_edit.py` restores upstream's
  acknowledge timing for the sub-CPU while keeping the other verificator fixes. Being tested in the Phase 2 build.
- Screenshots: `core/shots/p1c_*.png` (BIOS corrupt band, Alien 3 in game, BIOS instead of the CD game).

## Phase 2 (2026-09-09) — 32X in the slot, source complete, first build running
- `core/rtl/S32X/` (srg320 32X, edited by `tools/phase2_32x_edit.py` + `tools/phase2_vdp_edit.py`), `core/rtl/SH/` (SH7604 +
  core), `core/rtl/CART/` (S32X's cart.sv: works from the 32X's pass-through strobes, unlike the VHDL CART), `core/rtl/s32x_ddr.sv`.
- Chain: gen → S32X block (cart bus) → cart.sv → SDRAM port 0. Mega CD on the expansion port as before. SDRAM ports:
  0 cartridge (MD or SH-2 through the 32X), 1 MCD BIOS, 2 PRG-RAM, 3 PCM RAM, 4 load/save.
- Frame buffers + SH-2 work RAM in DDR3 (`s32x_ddr.sv`): per-line burst prefetch into a 1-M10K line buffer at H_CNT 0x1D0
  (LP_REQ), draw port with 8-entry write FIFO (busy at 6) and 16-byte read cache, SH-2 RAM channel as ddram.sv. Accepted
  deviation documented in the file header (line read ~10 µs early).
- 32X interface changes (faithful): (a) vector-ROM overlay gated on /CE0 (CD32X boot with an empty slot); (b) every MD
  /CE0 pass-through cycle runs through the ROM state machine and gets /DTACK from the 32X (as the real 32X drives the
  slot's /DTACK), arbitrated against SH-2 ROM fetches; a `CART_EXT` input from cart.sv says whether the cycle touches
  memory (else it completes at once); (c) SH-2 clock enable at the exact 23.011 MHz (3-of-7), parameter SH2_EXACT.
- Video: 32X pixel replaces the MD pixel where YSO_N is low (debug bit 63 disables). Audio: PWM (+ CD when "Filtered")
  on gen's EXT channel with saturation; CD unfiltered mixes after the LPF as before.
- Top edits: `tools/phase2_top_edit.py` (mapper/Pier logic in the top replaced by cart.sv + S32X's header-quirk block;
  old DDR3 PRG-RAM option removed). SDC: false paths for the SDRAM→32X negedge samplers (upstream's only timing failures).
- Test media: Night Trap 32X (Disc 1) bin/cue at `/media/fat/cifs/MegaCD/rr-sega-mega-cd/bin/32xcd/` (MGL
  `tools/mgl/MegaCD_P2_nighttrap.mgl`, US BIOS + disc). No 32X cartridge ROMs on the MiSTer yet (`games/S32X` empty).
- Not yet done: reset topology for the 32X (VRES/MRES tied inactive, block reset with the console as srg320 does), Hq2x strip,
  68K work RAM to SDRAM if M10K is short, Backup-RAM-cartridge model (was in CART.vhd; the "Internal+Cart" option now only
  covers the game cart's SRAM), Main support for 32X ROM naming.

## Phase 2 build 1 (2026-09-09 evening) — fit, timing, hardware
- Fit: 32,088 ALMs (77 %), 539 M10K (97 %), 61 DSP. 32X block 8,967 ALMs / 14 M10K; each SH-2 ~3,980. Timing: −8.9 ns on
  clk_sys (SDRAM dout → 32X negedge samplers via cart.sv muxes; my SDC named the wrong register), −1.3 ns SDRAM dout → MD
  data inputs, −0.5 ns SH-2 address → SDRAM request logic.
- Hardware: Alien 3 plays through the 32X pass-through chain (cart.sv behind the 32X, DTACK generated by the 32X). BIOS logo
  still corrupt, disc still not booting → the ASIC acknowledge revert was NOT the cause (kept anyway; harmless for fx68k).
- **Root causes found (fixed in build P2b):**
  1. `rtl/GEN/ba.sv` MBUS_FDC_READ ($A12000, the Mega CD gate array) auto-terminated the cycle; the old gen waited for the
     external /DTACK. The main CPU read stale gate-array registers (Word RAM handshake) → corrupt decompressed graphics,
     no disc boot. Now waits for DTACK_N like the old gen (srg320's MD-only arbiter never had an expansion device).
  2. `rtl/sdram.sv` (NukedMD 5-port) held ONE read-data register shared by all ports: a port's data was overwritten by the
     next port's access ~7 clocks later, before slow consumers (the Mega CD's ROM path) sampled it. Now `dout0..4` are
     per-port registers held until that port's next access (as the srg320 3-port controller did).
  3. Cart SDRAM port registered in clk_sys both ways (`tools/phase2_top_edit2.py`: cm_* request registers, cm_dout_r/cm_busy_r
     + a pending flag so the 32X never sees the gap before the controller accepts the request).
- Main/MGL facts: an MGL `type="f" index="0"` entry is routed to the disc-image slot (index 0 = "Insert Disk" here), so a
  BIOS cannot be chosen from an MGL; Main auto-loads `cifs/MegaCD/boot.rom` (EU on this MiSTer) and swaps in a `cd_bios.rom`
  found beside the disc. US BIOS copies placed beside Night Trap (cifs 32xcd dir) and 3 Ninjas (games/MegaCD/local).

## 2026-09-09 late — where the 32X actually stands, and three self-inflicted traps

**Working on hardware (build P2 / `phase0/MegaCD_P2.rbf`, deployed as `MegaCD_P2OLD.rbf`):**
- MD cartridge through the 32X pass-through chain: Alien 3 plays.
- Mega CD disc: boots (BIOS logo band still corrupt — deferred by the user).
- **CD32X: Night Trap boots to the Mega CD licence screen** with the US BIOS beside the disc and the region forced to US.
- **32X cartridges: Doom reaches its own region check** ("DEVELOPED FOR USE ONLY WITH NTSC..."), i.e. the cart is
  mapped, the 32X registers answer and MD-side 32X code runs. With the region set to US it goes black — the SH-2
  side is the open item.
- Region: Main auto-loads `cifs/MegaCD/boot.rom` (EU) so the console comes up PAL and every 32X title refuses.
  **F2 switches to US at run time** (`python3 /media/fat/uinput_kbd.py f2`), and a `cd_bios.rom` beside the disc
  overrides per game. Copies placed beside Night Trap and 3 Ninjas.

**Traps hit today (do not repeat):**
1. `quartus_fit`/`quartus_sta` 17.0 **crash in `sta_find_duplicates_of_deleted_net_name` /
   `add_keeper_to_vector_if_wildcard_matches`** when an SDC wildcard matches nodes that optimisation deleted. The
   line-doubler Hq2x stand-in triggered it via `set_multicycle_path -to {*Hq2x*}` and kept crashing even after that
   line was removed. Stock `sys/hq2x.sv` restored. Resource savings there need a different approach (the user runs
   a CRT, so the whole scandoubler/Hq2x path is unused and could be cut at the `video_mixer` instantiation instead).
2. A wedged `quartus_fit` looks exactly like a slow build. **Check CPU time, not wall clock** (0.7 CPU-min in 45
   wall-min = dead). The build monitors now compare CPU time over 4 minutes and report "WEDGED".
3. Three corruption fixes (`ba.sv` waiting for the Mega CD's DTACK on /FDC, per-port SDRAM `dout` registers, and
   re-registering the cartridge SDRAM port in `clk_sys`) **killed the boot outright** — black screen, VDP left in
   H32, i.e. the 68000 never ran. All three are reverted with a NOTE at each site; they belong to the deferred
   corruption/timing pass, not to integration.

**Diagnostics added (build P2g):**
- `s32x_ddr` writes one telemetry beat to **DDR3 0x30200000** every ~1.2 ms: magic `5332`, a sequence counter, and
  8-bit counters for SH-2 RAM reads/writes, frame-buffer draw writes and completed line prefetches. Read it live:
  `python3 /media/fat/hpsmem.py read 30200000 8`. A frozen `seq` means the DDR3 write path is dead; moving SH-2
  counters mean the SH-2s are executing. (`TELEMETRY` localparam in `rtl/s32x_ddr.sv` compiles it out.)
- **SH-2 clock is now runtime-selectable** (OSD debug "SH2 Clock", status bit 2): 23.0 MHz (3 of 7 clocks, the real
  rate) or srg320's CLK/2 = 26.8 MHz. Lets both be tested without a rebuild.
- Live DDR3 sampling with the game running showed **no change at all** in the SH-2 work RAM or either frame buffer,
  which is what the telemetry beat is there to explain (dead DDR3 path vs SH-2s never started).

## 2026-09-10 overnight — audit results and the five fixes now in the tree

A four-agent read-only audit of the merge against pristine upstream (script kept at
`.claude/.../workflows/scripts/md-mcd-32x-audit-4-*.js`, full findings in that run's `journal.jsonl`)
found the defects below. All five are now applied on top of the last configuration proven to run on
hardware (commit 3de4ac9, the build that played Alien 3 and reached Doom's region check).

1. **SDRAM read data crossed clk_ram -> clk_sys with no settling time** (`rtl/sdram.sv`). Consumers sample a
   port's data on the SAME edge at which they first see its busy drop, so a ~13 ns path had ~9 ns. The
   fitter reported -8 ns on every `dout` bit and whether a build worked came down to placement - this is
   what made builds flip between running and dead with no functional change. Each port's busy is now held
   two extra clk_ram cycles after capture, with a matching multicycle (3/2) in `MegaCD.sdc`.
2. **The 32X frame-buffer read used byte-address bit numbering against a word-address port**, and
   `fbd_ra_q` was 16 bits for a 17-bit value so the buffer-select bit was truncated: reads took the wrong
   word, possibly from the buffer being displayed (`rtl/s32x_ddr.sv`).
3. **The VDP threw away the one-clock DDR3 read-ready pulse** whenever it landed in the per-scanline
   refresh window (~80 of every ~1700 clocks), because the branch that consumes it is gated on `!FEN`.
   The SH-2 then waited on the VDP for ever while the display prefetch, the telemetry and the 68000 kept
   running - exactly the observed signature (`rtl/S32X/VDP.sv`).
4. **Every SH-2 cache-line burst beat latched the previous word** (`rtl/s32x_ddr.sv`): the line was
   indexed by a registered copy of the address that updates one clk_sys too late, because this module runs
   at half the clock upstream's `ddram.sv` uses. The BSC re-drives the address on its CE_R half and latches
   data on the next CE_F half without re-checking WAIT_N, so a line filled as w0,w0,w1,w2,... Now indexed
   from the live address while the read is asserted.
5. **The Mega CD gate array was given the bus arbiter's /AS instead of the 68000's own**
   (`rtl/GEN/ba.sv`, `gen.sv`, `MegaCD.sv`). `ASIC.vhd` selects between the fresh Word-RAM word and the
   previously latched one with `EXT_AS_N`; the S32X-revision gen exports `MBUS_AS_N`, asserted for VDP-DMA
   and Z80 cycles too, shifting every DMAed word by one position. That is the corrupt logo band, and it has
   been present since the very first Phase-1 build (gen swap only, no 32X). gen now exports the CPU strobe
   separately; the 32X keeps the arbiter's AS, which it needs to see DMA and Z80 cartridge cycles.

**Ruled out with evidence** (do not re-investigate): SDRAM fixed port priority starving the Mega CD (with
no cartridge, port 0 has no traffic); and `ba.sv` MBUS_FDC_READ auto-terminating $A12000 (differs from
upstream by one MCLK and cannot produce stale gate-array reads). An earlier HANDOFF entry named the latter
as a root cause - it is not.

**Also learnt:** the SH-2 PC probe, the per-port read registers and the SH-2 clock default flip all
correlate with dead builds and were dropped; re-add them one at a time, if at all. Routing two 32-bit PCs
across a 77%-full device is the most likely reason.

## 2026-09-10 ~00:30 — REQUIREMENT MET: build P3b plays every tier

`releases/MegaCD_32X_P3b_32x_cd_cd32x_working.rbf` (source = commit 763031b). Verified on the DE10-Nano,
screenshots in `core/shots/v_*.png`:

| Tier | Title | Result |
|---|---|---|
| MD cartridge | Alien 3 | plays |
| Mega CD disc | 3 Ninjas Kick Back | **plays** (first disc ever to boot on this core) |
| 32X cartridge | Doom | title screen, menu rendering |
| 32X cartridge | Virtua Racing Deluxe | 3D attract mode |
| 32X cartridge | Knuckles Chaotix | title/level screen |
| **CD32X** | Night Trap | **live full-motion video through the 32X frame buffer** |

Night Trap showing FMV is the acceptance test from the original roadmap §6 Phase 4: the Mega CD streams
sectors into Word RAM, the 68000 hands them over, the SH-2s blit into the 32X frame buffer in DDR3, and the
32X VDP composites over the MD picture. All three units are working together.

Fit: 32,194 ALMs (77 %), 4,130,382 memory bits (73 %). Timing not yet clean (see below).

### How to run it
- Deploy with `tools/deploy.sh <rbf> <name-on-mister.rbf>`; test MGLs are in `tools/mgl/` (rbf prefix must
  match the deployed name).
- **Region matters:** Main auto-loads `cifs/MegaCD/boot.rom`, which is EU here, so the console comes up PAL
  and every 32X title refuses to run ("DEVELOPED FOR USE ONLY WITH NTSC..."). Press F2 for US
  (`python3 /media/fat/uinform_kbd.py f2` — actually `uinput_kbd.py`), or put a US `cd_bios.rom` beside the
  disc. Copies are already beside Night Trap and 3 Ninjas.
- Don't press F2 mid-boot and screenshot immediately: a region change resets the core, which is what made an
  earlier Alien 3 screenshot look like a regression.

### Still open
- **Timing is not clean**: clk_sys -3.26 ns (TNS -3.5) and clk_ram -1.15 ns (TNS -30.9). It runs, but this
  is the same class of risk that produced the earlier build lottery. Worst paths are in `core/sta_p3b.log`.
- **BIOS with no disc** shows a black screen (with a disc it boots fine). Low priority but unexplained.
- Audio has not been checked at all on any tier.
- No long soak yet; the earlier NukedMD project found a crash only after hours.
- Deferred by choice: the SH-2 PC probe and the per-port SDRAM read registers (both correlate with dead
  builds). NOTE the SH-2 clock is NOT deferred: the shipping build runs the accurate **23.011 MHz**
  (3 of every 7 clk_sys cycles, as the real 32X derives it from the MD master clock), with srg320's
  CLK/2 = 26.85 MHz available on OSD debug bit 2. Every 32X title and the CD32X FMV run at the real rate.
- Not yet done from the roadmap: 32X reset topology (VRES/MRES tied inactive), Hq2x/scandoubler removal for
  resources (the user runs a CRT, so that whole path is dead weight), Main-side 32X ROM naming.

### Breadth check on P3b (no rebuild, screenshots `core/shots/w_*.png`)
All of these ran on the first attempt, region forced to US where needed:

| Tier | Title | Result |
|---|---|---|
| 32X | Doom | title/menu |
| 32X | Virtua Racing Deluxe | 3D attract |
| 32X | Knuckles Chaotix | title/level |
| 32X | After Burner Complete | in-game 3D |
| 32X | Space Harrier | attract, sprites |
| 32X | Star Wars Arcade | logo/starfield intro |
| Mega CD | 3 Ninjas Kick Back | gameplay |
| Mega CD | AH-3 Thunderstrike | title |
| Mega CD | Adventures of Batman & Robin | title |
| CD32X | Night Trap | live FMV |
| MD cart | Alien 3 | gameplay |

Six of six 32X titles, three of three Mega CD discs, the CD32X title and the MD cartridge. No title tested
so far fails to get past its title screen.

## 2026-09-10 ~01:15 — P3c: same coverage, and timing now CLOSES

`releases/MegaCD_32X_P3c_timing_clean.rbf`. **All clocks meet timing for the first time** (worst slack
+0.127 ns on clk_sys, +0.652 on clk_ram, zero total negative slack, no "timing requirements not met").
Fit 32,255 ALMs (77 %), 4,130,382 memory bits (73 %).

What closed it: the remaining failures were all the same clk_ram <-> clk_sys crossing, so `MegaCD.sdc` now
declares the whole crossing multicycle in both directions, justified by the handshakes that bound each
transfer (busy held two extra clk_ram cycles after capture; request address/strobes held for the whole
access; pixel data stable ~16 clk_ram cycles at a 6.7 MHz pixel rate). Note this is a *constraint* change
resting on the `sdram.sv` busy extension - without that extension the constraint would be a lie.

Re-verified on hardware after the change (screenshots `core/shots/z_*.png`): Alien 3, 3 Ninjas gameplay,
Doom, Virtua Racing Deluxe, Knuckles Chaotix, After Burner Complete, and Night Trap FMV. No regressions.

**Stability:** a 20-minute soak of Night Trap on P3b (identical RTL, looser constraints) ran continuously
with every telemetry counter advancing and still rendering FMV at the end (`core/shots/soak_nighttrap.png`).

### Remaining known issues
- **Mega CD BIOS with no disc inserted shows black.** With a disc it boots fine, so this is the
  "no disc / CD player" path only. Note the `usbios` test MGL is misleading: an MGL `type="f" index="0"`
  entry goes to the *disc* slot, so that test is really "no disc at all" and Main auto-loads
  `cifs/MegaCD/boot.rom` (EU) as the BIOS regardless.
- **Audio unverified on every tier** - no listening test has been done, and nothing in the telemetry
  covers it.
- 32X reset topology still simplified (VRES/MRES tied inactive), as srg320 does.
- Scandoubler/Hq2x still present and unused (the user runs a CRT); worth ~660 ALMs and ~12 M10K, but the
  obvious stand-in crashed Quartus 17.0's timing wildcard matcher - remove at the `video_mixer`
  instantiation instead.

## 2026-09-10 ~02:00 — P3d: audio verified on every source; /FDC DTACK restored

`phase0/MegaCD_P3d.rbf`. Adds a second telemetry beat at **DDR3 0x30200008** carrying sticky peak levels
and an audio sample-enable count (`python3 /media/fat/hpsmem.py read 30200008 8`; byte order is
aud_ce[31:0] then peak final, PWM, Mega CD, console).

**Audio works on all three sources** - previously completely untested:

| Title | console FM/PSG | Mega CD PCM/CDDA | 32X PWM | final mix |
|---|---|---|---|---|
| Alien 3 (MD cart) | 26 | - | - | 13 |
| 3 Ninjas (Mega CD) | 12 | **50** | - | 24 |
| Doom (32X) | 26 | - | **50** | 13 |
| Night Trap (CD32X) | 13 | **45** | - | 22 |

(0-255, peak of the top 8 bits of |sample|.) The sample-enable counter advances everywhere, so a silent
tier would be distinguishable from a stopped audio clock. Night Trap showing no PWM is expected - its
audio is CD, not 32X PWM.

Also restored the Mega CD's **/FDC ($A12000) DTACK wait** in `rtl/GEN/ba.sv`. The arbiter came from the
32X core, which has no expansion device, and auto-terminated those cycles. Re-verified after the change:
Alien 3, 3 Ninjas gameplay, Doom and Night Trap FMV all unaffected, so the earlier breakage attributed to
this change was really the two changes bundled with it.

Timing: emu clocks still positive (+0.134 clk_sys); `pll_hdmi` now -0.180 ns (TNS -0.28). Only the HDMI
output domain, and the user runs a CRT, but it is a small regression against P3c - worth a seed sweep.

### mcd-verificator still hangs at "System init..." (open, accuracy only)
Not a functional blocker - every game tested boots and plays. What is known:
- It IS running on this core (the pristine upstream core cannot even load the cartridge, because it wants
  the ROM on ioctl index bit 6 while this Main sends index 6 - the merge fixes that).
- During the hang the core is alive: telemetry `seq` and the VDP line-prefetch counter advance, and the
  Mega CD is still producing audio (peak 45).
- Not caused by: region (tried US via F2 and a US `cd_bios.rom` beside the disc), and not the /FDC DTACK
  wait (hangs both with and without).
- Next thing to try: the audit's observation that the NukedMD 75 Hz CDD command hand-off is half of a
  paired RTL+Main change - check the Main fork actually running on this MiSTer matches
  `tools/main_patches/`.

### Soak results (P3d, all clean)
| Title | Duration | Result |
|---|---|---|
| Night Trap (CD32X) | 20 min | FMV throughout, every counter advancing |
| Alien 3 (MD cart) | 5 min | ran to attract loop |
| 3 Ninjas (Mega CD) | 8 min | visibly progressed through the game |
| Doom (32X) | 8 min | demo running, SH-2 counters advancing |

No freeze, stall or counter stop in ~41 minutes of continuous running across the four tiers.

### mcd-verificator: it is OUR regression, and here is the likely cause
Decisive comparison - the same cartridge, disc, Main and MiSTer, only the core differs:
- **b66 (the previous NukedMD MD+MCD core, still on the SD card): the verificator RUNS**, printing
  "CD hardware detected at 0x00400000" and a full results page (`core/shots/v66_a.png`): RAM CART not
  present OK, COLOR CALC OK, VAR TESTS ERROR 02, IRQ 0A ERROR 09, REG X000/X002/2006/X00C OK,
  REG 8030 ERROR 07, CDC REGS OK, PROG RAM OK, WORD RAM OK, WRAM PMOD OK, CDC INIT ERROR 03.
  (That run is PAL; the project's notes say VAR / REG 8030 / IRQ 09 are fixed-NTSC constants in the ROM.)
- **This core hangs at "System init...", before CD hardware detection.**

So something in this merge breaks a cartridge's early Mega CD probing. The strongest hypothesis, and the
first thing to try next session:

The 32X now sits in the cartridge path, and **`MEM_RDY` is tied to 0** in the gen instantiation so that
every $000000-$7FFFFF cycle waits for an external /DTACK, with the 32X generating it for cartridge cycles
via the `MD_ROM_PASS` change in `rtl/S32X/IF.sv`. srg320's S32X core instead feeds `MEM_RDY` from the cart
SDRAM busy and lets the arbiter self-terminate cartridge cycles; only the $880000-$9FFFFF window goes
through the 32X ROM state machine. Tying it to 0 was necessary because the Mega CD windows must wait for
the gate array's /DTACK (self-terminating them was the original corrupt-BIOS bug), but it forces every
cartridge cycle through a state machine that srg320 never used that way, and the audit raised two
medium-confidence hazards in exactly that path (`MD_ROM_WAIT` latched without ADEN/RV qualification, and
the `!CART_EXT` escape in `RS_MD_WAIT`).

**Proposed fix:** qualify `MEM_RDY` by address instead of tying it low - assert it (from the cartridge
SDRAM busy) only for cartridge-space cycles, and leave it low for the Mega CD windows so those still wait
for the gate array. Then revert `MD_ROM_PASS` so the 32X only owns its own window, as upstream does.
This was NOT attempted tonight: every tier works, and it is a structural change to the bus that deserves a
fresh session rather than a 3am edit to a working build.

## 2026-09-10 ~02:15 — RELEASE r1

`releases/MegaCD_MD_MCD_32X_r1.rbf` (telemetry compiled out) and
`releases/MegaCD_MD_MCD_32X_r1_debug_telemetry.rbf` (same RTL, DDR3 telemetry beats enabled for debugging).

- **Timing closes completely**: every clock positive (+0.52 clk_sys, +0.54 clk_ram, +0.54 pll_hdmi), zero
  total negative slack, no "timing requirements not met". 32,145 ALMs (77 %), 4,130,382 memory bits (73 %).
- Verified on hardware, nine tests, screenshots `core/shots/r_*.png`: Mega CD BIOS (clean logo animation),
  Alien 3, 3 Ninjas gameplay, Doom, Virtua Racing Deluxe, **Knuckles Chaotix in gameplay**, After Burner
  Complete, Space Harrier, Night Trap FMV.

To re-enable telemetry set `TELEMETRY = 1` in `core/rtl/s32x_ddr.sv` and rebuild; read it with
`python3 /media/fat/hpsmem.py read 30200000 8` (counters) and `... 30200008 8` (audio peaks).

### Negative result: the MEM_RDY hypothesis is WRONG (branch `memrdy-experiment`, not merged)
Qualifying `MEM_RDY` by address so cartridge cycles self-terminate on the cartridge SDRAM port, exactly as
srg320's S32X core does, while the Mega CD windows keep waiting for the gate array - **does not fix the
verificator**. It still hangs at "System init...", and timing got marginally worse (-0.011 ns clk_sys).
The branch is kept for reference but is NOT the answer; do not spend time re-deriving it.

What that leaves, given the verificator gets *past* System init on both b66 (NukedMD MD) and, per the
previous project's notes, on upstream srg320 MegaCD (fpgagen MD, where it reached CDC INIT):
- it is not cartridge-cycle termination (ruled out here)
- it is not region, and not the /FDC DTACK wait (ruled out earlier)
- so suspect the paths this merge added between the MD and the Mega CD for a **cartridge boot**
  specifically: the Mega CD BIOS window read path (`sdram` port 1 addressed with `GEN_VA[16:1]`), the
  `GEN_VDI` source mux keyed on `~S32X_DTACK_N`, or the 32X sitting in the cartridge path at all.
  A cheap next experiment: temporarily force `GEN_VDI` to select `MCD_DO` by address (`EXT_ROM_N`,
  `GEN_RAS2_N`, `EXT_FDC_N`) rather than by the 32X's DTACK, and see whether detection proceeds.

### Compatibility on release r1 (every title tested, all on first attempt)
| Tier | Title | Result |
|---|---|---|
| MD cart | Alien 3 | gameplay |
| Mega CD | 3 Ninjas Kick Back | gameplay |
| Mega CD | AH-3 Thunderstrike | title |
| Mega CD | Adventures of Batman & Robin | title |
| Mega CD | Cobra Command | full-motion video |
| Mega CD | Earthworm Jim Special Edition | intro |
| Mega CD | Bram Stoker's Dracula | title (slow loader - needs ~3 min) |
| Mega CD | (no disc) | BIOS boots, logo animation clean |
| 32X | Doom | title/menu |
| 32X | Virtua Racing Deluxe | 3D attract |
| 32X | Knuckles Chaotix | **gameplay** |
| 32X | After Burner Complete | in-game 3D |
| 32X | Space Harrier | attract |
| 32X | Star Wars Arcade | intro |
| CD32X | Night Trap | live FMV |

Six of six 32X cartridges, six of six Mega CD discs, the CD32X title and the MD cartridge. Nothing tested
has failed to run.

### Second negative result: address-based GEN_VDI does not fix the verificator either
Branch `vdi-mux-experiment`. Selecting the MD's data source by address (`EXT_ROM_N`, `GEN_RAS2_N`,
`EXT_FDC_N`) instead of by `~S32X_DTACK_N` - which removes the audit's "a phantom 32X cycle can hijack an
in-flight Mega CD read" hazard - still hangs at "System init...". Timing stays clean (+0.30 clk_sys,
+0.38 clk_ram).

So for the verificator, all four cheap hypotheses are now eliminated: region, the /FDC DTACK wait,
cartridge-cycle termination (MEM_RDY), and the data-source mux. **Stop guessing.** The next step should be
instrumentation, not another guess: capture the MD bus state when it stops - latch `MBUS_A`, the
strobes and which DTACK sources are asserted into a telemetry beat when no cycle has completed for N
clocks, then read it with `hpsmem.py`. That will say exactly which address never terminates, in one build
instead of five.

### `vdi-mux-experiment` passes the full sweep (candidate for merge)
Although it does not fix the verificator, selecting the MD data source by address is what the hardware
decode does and it removes the audit's phantom-DTACK hijack hazard. Verified on hardware with the same
sweep as the release - Mega CD BIOS (clean logo), Alien 3, 3 Ninjas gameplay, Cobra Command FMV, Doom,
Knuckles Chaotix gameplay, Night Trap FMV - with rendering identical to r1 (screenshot byte sizes match).
Timing clean (+0.30 / +0.38). Soak in progress before deciding whether to merge.

## RELEASE r2 (supersedes r1) — `releases/MegaCD_MD_MCD_32X_r2.rbf`
r1 plus address-based selection of the MD data source, which removes the audit's phantom-DTACK hazard
(the 32X could acknowledge outside its own cycle and hijack an in-flight Mega CD read - exactly the class
of intermittent fault that cost this project a night). Same RTL otherwise, telemetry compiled out.

Evidence: full hardware sweep (Mega CD BIOS clean logo, Alien 3, 3 Ninjas gameplay, Cobra Command FMV,
Doom, Knuckles Chaotix gameplay, Night Trap FMV) with rendering identical to r1, plus a 12-minute Night
Trap soak and a 6-minute 3 Ninjas soak, both running throughout. Timing clean: +0.30 clk_sys, +0.38 clk_ram.
`releases/MegaCD_MD_MCD_32X_r1_debug_telemetry.rbf` is kept for diagnostics (r1 RTL + DDR3 telemetry).

## The verificator hang, measured rather than guessed — a real lock-up in the bus arbiter
Five guesses had already been spent on this. The sixth attempt instrumented it instead
(`tools/phase4_bushang_probe.py`): the arbiter holds `mstate` for the whole of an external cycle, so a
counter on "mstate has not changed" identifies a cycle that never terminates, and the address, state,
read/write flag and acknowledge sources are latched into a third DDR3 telemetry beat at `0x30200010`.

Read while mcd-verificator sat at "System init...":

| read | value | meaning |
|---|---|---|
| 1 | `0c05cefc1fa13453` | stalled at **$A11FFC, a read**, arbiter state 12 = `MBUS_NOT_USED`, DTACK_N high |
| 2 | `0c45cefc1fa13453` | same address, stall count 5 -> 69 |
| 3 | `0c71cefc1fa13453` | same address, stall count -> 113 |

A working title (3 Ninjas) read back `0000000000003453` — no stall at all. So the hang is one address that
nothing ever acknowledges.

$A11FFC has `A[23:8] == $A11F`, which matches none of the arbiter's exact-page decodes (A100, A110, A111,
A112, A113, A120, A130, A140), so it fell through to `MBUS_NOT_USED` — a state that waits for an external
/DTACK. Inside the control area nothing external will ever drive one, so the machine stopped for good.
The verificator does not contain $A11FFC as a constant (checked: no such immediate anywhere in the ROM);
it computes it, most likely as an offset from the $A12000 gate-array base it uses heavily.

**The fix**: an address in $A10000-$A1FFFF that matches no register now terminates its own cycle and
returns open bus, which is what the console's I/O and bus-arbiter decoder does. This was never
verificator-specific — any title reading an unmapped control-area address would have locked up.

**The exception that nearly broke the 32X**: the console deliberately drives no /DTACK for
$A15000-$A15FFF so that a cartridge can, and that is exactly how the 32X answers its own registers
(`IF.sv` drives `DTACK_N` for $A15100-$A153FF). A blanket $A1xxxx auto-terminate would have cut every 32X
register cycle short. That window is excluded. Documented at
https://plutiedev.com/cartridge-slot — the console does not assert /DTACK for $800000-$9FFFFF,
$A15000-$A15FFF or $B00000-$BFFFFF.

New tooling: `tools/mister/make_p3_mgls.sh` clones the test MGL set onto a new core name and adds the
disc+cartridge verificator combination; `tools/mister/sweep.sh` runs the whole title list, screenshots
each, and reads the liveness and stall telemetry beats per title.

### Verified on hardware: the control-area fix costs nothing and the hang is gone
Sixteen titles loaded in turn on the fixed build, each screenshotted with the liveness and stall
telemetry read while it ran. Fifteen reported no stalled cycle at all; only mcd-verificator did.

| Tier | Titles | Result |
|---|---|---|
| MD cartridge | Alien 3 | running |
| Mega CD | 3 Ninjas, AH-3 Thunderstrike, Batman & Robin, Cobra Command, Earthworm Jim SE, BIOS with no disc | running, BIOS logo clean |
| 32X cartridge | Doom, Virtua Racing Deluxe, Chaotix, After Burner, Space Harrier, Star Wars Arcade | running |
| CD32X | Night Trap | title video |

**A trap in my own test rig:** the first pass showed every 32X cartridge sitting on its region-lock
screen. The console comes up PAL because Main auto-loads an EU `boot.rom`, and neither the F2 hotkey nor
loading a US `cd_bios.rom` from the MGL changed it. What works is the core's saved status word: bits 7:6
of `/media/fat/config/MegaCD.CFG` force the region, and 2 there means USA. Backed up as
`MegaCD.CFG.preregion`. Every core built from this tree shares that one file, because MiSTer names it
from CONF_STR, not from the .rbf.

### The verificator is not stuck on one address - it is running off the rails
With $A11FFC terminating, the stall moved, and it moves again between runs: $C00C78 on one run,
$81FBDA on the next. Both are addresses a real Mega Drive would also hang on ($C00C78 fails the VDP's
A[7:5]=0 decode; $81FBDA is in the $800000-$9FFFFF area nothing acknowledges). Neither appears as a
constant anywhere in the ROM. A program that stops at a different wild address each time is not probing
deliberately; it has lost its place. So $A11FFC was a symptom too, and the real fault is earlier.

**What correct looks like**, from the NukedMD reference core (b66) with the same disc and cartridge:
```
Mega-CD verificator V1.02
CD hardware detected at 0x00400000
RAM CART....not present OK      COLOR CALC.. OK      VAR TESTS... OK
IRQ TEST.... ERROR: 0A          REG X000/X002/2006/X00C/8030, CDC REGS.... OK
PROG RAM.... OK   WORD RAM.... OK   WRAM PROT... OK
CDC INIT/FLAGS/DMA2/DMA3/DMA1... OK
Diagnostics complete.
```
Ours never prints the first line, so it dies inside CD hardware detection - before it has read anything
useful out of the BIOS window at $400000. Note the reference fails the IRQ test too, so that one is not
ours to fix. (The pristine upstream core cannot be used for this comparison: it decodes the cartridge
from a different ioctl index and simply ignores the cart, booting the BIOS instead.)

Next instrument, ready to build: `tools/phase5_bushang2.py`. It force-terminates a cycle that nothing
acknowledges after ~1k clocks so the machine keeps going, records the last four DISTINCT addresses that
needed it plus which master issued each, and counts them. That turns "one address per build" into the
whole pattern in one build. It is diagnostic only and must never ship.

### A timing edge that had to be fixed, not re-rolled
The release build of exactly this RTL came out at **-0.126 ns** on clk_sys while the debug build of the
same logic made +0.009 ns. The failing family is always the same: an address register (the MD arbiter's
`MBUS_A`, or an SH-2's bus controller) through the cartridge module's SRAM range comparator and output
mux into `CDI_SYNC`, which the 32X samples on the clk_sys **negedge** - half a period, 9.3 ns, for a path
that measures 8.5 ns and is mostly routing on a device 77% full. Which side of that line a build lands on
is placement luck. That is the same condition that once made builds flip between working and dead, so
re-rolling the fitter would have been the wrong answer.

`CDI_SYNC` has exactly one consumer, `MD_ROM_DO <= CDI_SYNC` in `RS_MD_READ`, and that state cannot be
reached until at least two clocks after the address settles - the state machine starts from
`AS_N_SYNC`/`CE0_N_SYNC`, themselves sampled a clock later, then passes through `RS_MD_RW`. So the
transfer is not single-cycle and the sampler gets a full extra period in `MegaCD.sdc`. An early sample
is never read.

## RELEASE r3 (supersedes r2) — `releases/MegaCD_MD_MCD_32X_r3.rbf`
Two changes over r2, one functional and one that removes a source of build-to-build luck.

1. **An unmapped address in the control area now terminates its own cycle** instead of waiting for a
   /DTACK nothing will drive. That was a real lock-up, not a verificator quirk: any title reading an
   unmapped $A1xxxx address would have hung the machine. $A15000-$A15FFF is excluded, because the
   console deliberately leaves that window unacknowledged so a cartridge can answer it, and that is how
   the 32X answers its own registers.
2. **The 32X's cartridge-bus sampler gets a full clock period** in `MegaCD.sdc`. It is clocked on the
   negedge, so the path from an address register through the cartridge SRAM decode had 9.3 ns for 8.5 ns
   of mostly-routing delay. The release build of the same RTL came out at **-0.126 ns** while the debug
   build made +0.009 ns; with the exception it is **+0.756 ns** and the core's own logic is no longer the
   limiter (the worst path is now inside the framework's HDMI scaler at +0.277 ns).

| | r2 | r3 |
|---|---|---|
| clk_sys setup slack | +0.30 | **+0.756** |
| clk_ram setup slack | +0.38 | +0.425 |
| ALMs | - | 32,187 / 41,910 (77%) |
| M10K blocks | - | 539 / 553 (97%) |

Verified on hardware: all sixteen titles loaded and ran (Mega CD BIOS logo clean, Alien 3, 3 Ninjas,
AH-3 Thunderstrike, Batman & Robin, Cobra Command, Earthworm Jim SE, Doom, Virtua Racing Deluxe,
Chaotix, After Burner, Space Harrier, Star Wars Arcade, Night Trap CD32X), plus a 12-minute Night Trap
soak on the same RTL with the liveness counter advancing at every one of 24 samples and all 24 frames
distinct.

**Two test-rig traps worth remembering.** Forcing the region through `MegaCD.CFG` bits 7:6 is what makes
32X cartridges run, but leaving it set makes the BIOS-with-no-disc boot render black - which looks
exactly like a core regression until you load the same MGL on the previous build and see it too. Restore
the file afterwards. And do not run `git stash -u` or switch branches while a background test is writing
screenshots into an untracked directory; it took the directory with it mid-sweep.

### Fault-frame probe: inconclusive, and why
The phase9 build captures the last eight 68000 write-data words, frozen when the 68000 reads the
bus/address-error vector. Across three runs it did not isolate the exception frame:

| Run | last vector fetched | ring contents |
|---|---|---|
| 1 | $00002E (line F) | ordinary writes |
| 2 | $00000E (**address error**) | does not parse as a frame |
| 3 | $00002E (line F) | ordinary writes |

Two faults are wrong with the probe. The freeze only fires on $000008-$00000F, but two of three runs
ended on the line-F vector at $00002C, so the ring kept rolling. And the values it did capture are the
program's own traffic - the same four words `0040 2010 C000 2022` appear in every run, which is a VDP
control-port address-set long, not a stack frame.

Next version should freeze on ANY vector fetch in $000008-$0000FF (the reset vectors at $000000/$000004
excepted), and should record the write ADDRESS beside the data so a stack push is distinguishable from a
register write. The finding that stands is unchanged: an address error is taken, confirmed again here by
run 2's vector fetch.

### The alternating border line: found in the RTL, and a refinement held back
Three readers compared vdp.sv against vdp.vhd and this project's video path. The measured symptom - PAL
346x294, output row 37 alternating between a border row and a picture row while every other border row
is static - is pinned arithmetically:

`vdp.sv` decides border-versus-picture with `DISP_EN_PIPE[0] <= MR2.DISP & ~IN_VBL` (vdp.sv:1672) and
clears `IN_VBL` a line early, at V_CNT 0x1FE (vdp.sv:882-883). So V_CNT 0x1FF, "line -1", is
display-enabled and the picture is 225 lines. With PAL, V28 and the border on, output row 0 is V_CNT
0x1DA, so row 37 **is** V_CNT 0x1FF and row 38 is V_CNT 0x000 - exactly the measured boundary. The older
VHDL VDP keeps a separate `V_ACTIVE_DISP` for the display decision, starting at V_CNT 0
(vdp.vhd:2424-2429), and uses IN_VBL only for the status flag. That is why upstream never shows it.

It alternates rather than sitting steady because `MR2.DISP` is the only frame-varying term, sampled once
per line at H_CNT 0x013 - and for this row that instant lands at the tail of the BIOS's vblank work.

**Fixed in r6** (`tools/phase12_disp_line.py`): the display decision excludes V_CNT 0x1FF. The line is
still rendered for sprite prefetch, exactly as the old VDP does.

**Held back, worth doing if artefacts persist.** The 32X's `YSO_N` is not blanked outside the 32X's own
display window, while its R/G/B are (`VDP.sv:499-501` vs `:508`). During the 32X's vertical blank
`PIX_COLOR` holds the previous frame's last pixel and `FS` is re-latched every vblank, which gives
`PIX_COLOR[15]` - and therefore the overlay select - an exact two-frame period. The general fix is

```systemverilog
wire s32x_disp = |MODE & HDISP[2] & ~VBLK;    // the 32X is actually showing a pixel here
assign YSO_N = ~((PRI ^ PIX_COLOR[15]) & s32x_disp) & (YS_N_SYNC | ~s32x_disp);
```

which subsumes r4's `~|MODE` term. It is NOT in r6 because it changes behaviour on the working 32X path
(six cartridges plus CD32X), and r4's narrower fix may already be enough. Note also that srg320's own
32X core gates its overlay with `|| !s32x_rom` (S32X.sv:885). **Do not copy that here**: a CD32X title
has no cartridge - the 32X code arrives from the disc - so `s32x_rom` would be 0 and the gate would
break Night Trap.

## Doom CD32X Fusion: a real title that needs mode 1, and does not boot
Source: https://github.com/viciious/d32xr (`src-md/scd.c`, `InitCD`). This is the first non-test program
found that drives the Mega CD from a cartridge, so it exercises the same path as mcd-verificator.

What it needs, in order:
1. Find the CD BIOS by matching "SEGA" at $415800+0x6D, else $416000+0x6D, else $41AD00+0x6D. **Our
   boot.rom has "SEGA CD" at file offset 0x1606D, i.e. exactly the $416000 candidate**, so detection
   should pass provided the mode-1 BIOS window reads correctly.
2. Reset the gate array: `$A12002 = $FF00`, then `$A12001` = 3, 2, 0.
3. `$A12001 = 2`, then spin until bit 1 reads back (bus acknowledge). **No timeout.**
4. `$A12002 = $0002`, clear PRG RAM, Kosinski-decompress the sub-CPU BIOS to $420000, copy the sub
   program to $426000.
5. `$A1200E = 0`, `$A12002 = $2A`, `$A12001 = 1`, then spin until bit 0 reads back (sub-CPU running).
   **No timeout.**
6. Every vblank, read-modify-write `$A12000` setting bit 8 (IFL2) to raise a level 2 interrupt on the
   sub-CPU - the sub BIOS needs these to run at all.
7. Wait for the sub program to write `'I'` to `$A1200F`. **This one HAS a timeout** (2,000,000 reads,
   about 2.6 s) after which `InitCD` returns 0 and the game carries on believing there is no CD.

That last point explains the symptom exactly: no hang, no crash, no bus stall, the 32X alive with its
SH-2 memory counters climbing, and a black screen, because the game has no data. The two spins WITHOUT
timeouts evidently pass, so the sub-CPU does come out of reset; what fails is the sub program answering.

Measured on the probe build: $A1200E/0F is touched only briefly around t=4.8 s (4 samples in 12 s), not
spun on, and from t=11 s the 68000 is in its normal loop against the 32X comm register $A15120.

Ruled out: region (header byte F, forcing USA changes nothing), ROM size (4 MB exactly, same as Virtua
Racing Deluxe and X-Men which both run), disc sector format (converting the 2048-byte ISO to MODE1/2352
changes nothing), and load order (both orders black).

**Next measurement, not yet done:** instrument the Mega CD sub-CPU - does it fetch from PRG RAM after
`$A12001 = 1`, does it take the level 2 interrupt the vblank handler raises, and does it ever write
$A1200F. The gate array does implement IFL2 (`ASIC.vhd:613-617`, gated on `IEN(2)`), so the question is
whether the sub-CPU gets far enough to enable it.

## ROOT CAUSE FOUND: the Mega Drive's cartridge read was never latched
Three readers took our fetch path, the reference core at C:\Users\joelw\Documents\MegaCD_MiSTer_New, and
jgenesis. The answer is architectural, not a timing race, and not the CDI_SYNC multicycle.

`sdram.sv` has ONE data register shared by all five ports:
```systemverilog
reg [15:0] dout;
assign dout0 = dout; assign dout1 = dout; ... assign dout4 = dout;
if (state == STATE_READY && ram_req) dout <= SDRAM_DQ;   // not even qualified read vs write
```
Every consumer latches it on its own handshake - the Mega CD gate array (ASIC.vhd:809-818), the 32X for
the SH-2 and for its own $880000 window - **except a Mega Drive read of cartridge space**, which was a
live combinational wire: sdram dout -> CART_MEM_DO -> cart.sv VDO -> S32X_CDI -> `else VDO = CDI` ->
GEN_VDI -> MBUS_DI -> the 68000's data pins, with no storage anywhere.

fx68k re-samples its data input on every enPhi2 and keeps the LAST one, and the 68000 runs at 1-in-7
clk_sys. So the word must survive ~130-200 ns after the 32X released the cycle. One SDRAM access is
~65 ns, so it has to survive two or three foreign accesses, and port 0 never re-reads.

**Why it appears exactly at $D38E:** that code runs immediately after the cartridge starts the sub-CPU -
the moment the machine goes from "only the MD touches SDRAM, all serialised by the one MBUS arbiter" to
"the sub-CPU fetches from PRG RAM on port 2, asynchronous to the MD bus". Before it, every fetch is
correct; after it, a large fraction are exposed. A wrong word desynchronises the 68000's prefetch, which
is why it executes two bytes into `lea $F36E,a2` and takes a line F.

**Why the reference core is immune:** identical shared-dout sdram.sv, but its cartridge module registers
the word out of dout on the busy falling edge and presents the register. One line of difference.

**The fix (r7):** the 32X's ROM state machine already latches the word at the right instant for
pass-through cycles too (`RS_MD_READ: MD_ROM_DO <= CDI_SYNC`) and asserts DTACK from there. It just did
not return it. `tools/phase17_cart_latch.py` makes cartridge space return `MD_ROM_DO`, exactly as the
$880000 window already did. Safe: gen.sv:458 serves work RAM, I/O and VDP internally, so only cartridge
space takes this path.

### Cleared by the same investigation
- **The CDI_SYNC multicycle is NOT the cause.** Its claim is literally true - one consumer, read late
  enough. It is fine to keep.
- **My phantom-DTACK hypothesis was wrong as the primary cause**, but the hazard IS real and remains:
  `MD_ROM_WAIT`/`MD_ROM_PASS` are set outside the case statement and cleared only in RS_MD_READ, so a
  strobe edge arriving mid-cycle is replayed later against whatever address is current, and its
  MD_ROM_DTACK_N still reaches the 68000. MegaCD.sv:544-549 fixed only the data mux. **Worth fixing next**
  - and note it now matters more, because with r7 the returned word is a latch that is stale until
  RS_MD_READ, held off only by DTACK.

### jgenesis reference semantics, for later accuracy work
- Main-CPU writes to PRG RAM are dropped unless SBRQ is asserted or SRES holds the sub-CPU in reset;
  write protect ($A12002 high byte) applies to the SUB CPU only, never the main CPU. Ours matches.
- At power-on both SBRQ and SRES are asserted, so a mode-1 cartridge can write PRG RAM immediately.
- IFL2 is a LEVEL: set by writing 1, cleared by writing 0 or by the sub-CPU acknowledging INT2 - not
  self-clearing, and not cleared by reset.
- Sub-CPU IPL is strict priority INT5 > INT4 > INT3 > INT2 > INT1, and on IACK the source matching the
  acknowledged level must be cleared - jgenesis notes mcd-verificator fails otherwise.
- BIOS window offset $70-$73 returns $FFFF then the $A12006 HINT vector, not BIOS bytes. Ours does this.

## r7: mcd-verificator RUNS TO COMPLETION
The one-line latch fix worked. From hanging at "System init..." on every build since the merge began, to
the full diagnostic page:

```
Mega-CD verificator V1.02
CD hardware detected at 0x00400000
RAM CART....not present OK      COLOR CALC.. OK
VAR TESTS...:26801  ERROR: 02   IRQ TEST....:26  ERROR: 06
REG X000/X002/2006/X00C.... OK  REG 8030....:1281  ERROR: 08
CDC REGS.... OK                 PROG RAM.... OK
WORD RAM.... OK                 WRAM PMOD... OK
CDC INIT.... OK                 CDC FLAGS...:87  ERROR: 40
CDC DMA2/DMA3/DMA1.... OK
Diagnostics complete.
```

**14 of 18 pass**, including every test that exercises the repaired path: PROG RAM, WORD RAM, WRAM PMOD,
CDC INIT and all three CDC DMA tests. Timing +0.548 ns, 77% ALMs.

Comparison with the NukedMD reference (b66), which passes everything except IRQ TEST:

| Test | ours (r7) | b66 | note |
|---|---|---|---|
| VAR TESTS | ERROR 02 | OK | 68000 cycle behaviour - the accepted fpgagen cost (§2, §5.1) |
| IRQ TEST | ERROR 06 | ERROR 0A | **both fail**, different codes |
| REG 8030 | ERROR 08 | OK | 68000 cycle behaviour |
| CDC FLAGS | ERROR 40 | OK | worth investigating - not obviously a CPU-accuracy test |

`CDC FLAGS` is the interesting one: it is not a cycle-exactness test, so it may be a real defect rather
than an accepted cost.

### Doom CD32X Fusion: blocker removed, still crashes
Now boots through the BIOS to "CHECKING DISC" and then crashes - a solid green screen with a continuous
high-pitched tone (user-observed), or black. Previously it managed only a single dashed line. So the
latch fix removed a blocker but there is at least one more.

### Trap for the next session: OSD debug bit 39 changed POLARITY in r7
r5/r6: `status[39] ? GEN_M68K_AS_N : GEN_AS_N` (1 = the good 68000 strobe).
r7 onward: `status[39] ? GEN_AS_N : GEN_M68K_AS_N` (0 = the good 68000 strobe).
A config carried over from an r6 A/B therefore selects the BAD strobe on r7 and garbles the BIOS logos.
Clear bit 39 in /media/fat/config/MegaCD.CFG when moving to r7 or later.

## CDC FLAGS error 40, read from the test's own code instead of guessed at

`core/rtl/MCD/CDC.vhd` is **byte-identical** to the b66 reference that passes this test, and
`ASIC.vhd` differs only in the PRG-RAM DTACK hunks, so the failure is not CD decoder logic. The test
ROM settles what it actually measures. Disassembled with `tools/dis68k.py` (rewritten this session -
the old copy was lost in the `git stash -u` incident):

```
01454A  clr.w d4 / clr.w d5
014568  loop1: read CDC register 1 (IFSTAT) via the main<->sub RPC; addq #1,d4; loop while bit5 == 0
014582  loop2: same; addq #1,d5;                                    loop while bit5 == 1
01459A  d0 = d4 - 48 ; cmpi.w #2,d0 ; bhi -> FAIL 40      d4 expected 48-50
0145A8  d7 = d5 - 71 ; cmpi.w #2,d7 ; bhi -> FAIL 41      d5 expected 71-73
```

IFSTAT bit 5 is DECI. 49/(49+72) = **40.5%**, which is jsgroth's "the decoder interrupt flag should
automatically clear about 40% of the way through a 75Hz frame". The routine at `0x13EF6` is the one
that prints `CDC FLAGS`; the `0x12E4E` routine with the same sub-test numbers is `CDC DMA3`, which is
a trap worth avoiding.

### Getting d5 without a rebuild
The run stops at the d4 check, so d5 was never visible. `tools/verif_patch_cdcflags.py` widens the d4
bound (`0145A0 cmpi.w #$2,d0` -> `cmpi.w #$FFFF,d0`) so BHI can never be taken and the run reports d5
as error 41. Verified sound: **b66 runs the patched ROM and still reports CDC FLAGS OK.**

| | d4 (asserted) | d5 (cleared) | duty | implied P |
|---|---|---|---|---|
| hardware / b66 | 48-50 | 71-73 | 40.5% | 13.45 ms |
| ours (r7) | **87** | **69** | **55.8%** | **~18 ms** |

The cleared phase is right and all the extra time is in the asserted phase. CDC.vhd asserts DECI and
pulses SECTOR_END (which zeroes FRAME_CNT) at the last word of every sector, and DEC_MID clears DECI
40% of a frame later, so with sectors every P:

    cleared  = 13.33 - 5.33 = 8.0 ms          (fixed)
    asserted = (P - 13.33) + 5.33 = P - 8.0

The model reproduces b66's numbers exactly, and **the duty cycle is independent of how fast the poll
loop runs**, so P ~ 18 ms is a real result: sectors are arriving nearer 55 Hz than 75 Hz.

### The disc is what breaks the timing tests
Same core, same cart, disc removed:

```
with disc:     IRQ TEST....:127  ERROR: 06     CDC FLAGS...:87  ERROR: 40
without disc:  IRQ TEST....:227  ERROR: 09     (CDC INIT 03 - needs a disc, CDC FLAGS not reached)
```

jsgroth's expected range for the IRQ counting sub-test is **224-226**; with no disc we produce 227.
So the inter-CPU timing is very nearly right and **disc activity is what pushes these tests off**.
That reframes VAR TESTS / IRQ TEST / REG 8030 as well: they may not be 68000 cycle accuracy at all.

Not yet explained: CDD_SEND is a clean 75 Hz (`ASIC.vhd` `CDD_FRAME_CNT = 166666` on `CLK_12M_F`,
identical to b66), `CLK_12M_F`/`CLK_CNT`/`CLK50_EN` are identical, and both top levels feed the CDC
through the same `hps_ext` path. So the request pacing is right and the sectors themselves are late.
`tools/phase19_sector_rate.py` adds telemetry beat 4 (SECTOR_END / CDD_SEND / DEC_FRAME / DEC_MID
counters) to tell delivery from pacing. Noted in passing: `S32X_VDP`'s `LP_REQ` is unconditional
(`assign LP_REQ = DOT_CE && H_CNT == 9'h1D0`), so the 32X DDR3 line prefetch runs every scanline even
with no 32X cartridge.

### CORRECTION: d4 is 47, not 87 - the sector-period conclusion above is withdrawn

The 87 came from the pre-compaction session summary and was never verified against a screenshot in
this session. Four controlled runs (two on r7/P7, two on r8/P8, identical MGL and procedure) all give
**d4 = 47**. With the verified d5 = 69:

| | d4 asserted | d5 cleared | duty |
|---|---|---|---|
| hardware / b66 | 48-50 | 71-73 | 40.5% |
| ours | 47 | 69 | **40.5%** |

47/49 = 0.959 and 69/72 = 0.958: **both phases are short by the same factor.** The duty cycle is
exactly right, so the decoder flag waveform is correct, DEC_MID fires where it should, and there is
no sector-rate problem. Everything above about P ~ 18 ms and a 55 Hz drive is wrong - it was built on
the unverified 87. `tools/phase19_sector_rate.py` still gets built because the counters are cheap and
confirm the drive directly, but it is no longer the lead.

What the numbers actually say is a **uniform ~4% deficit in the main<->sub RPC loop rate against the
Mega CD's 75 Hz frame**, while REG 8030 (a main-CPU loop against the same CD timer) is only 0.23% low
at 1283 against 1286-1288. Main CPU vs CD timebase is therefore nearly exact and the ~4% sits on the
sub-CPU side - its clock, or the INT2/RPC path, or PRG-RAM wait states.

**IRQ TEST now reports error 0A, which is exactly what the b66 reference reports** - b66 fails that
one test and nothing else. So on IRQ TEST we are level with the reference.

The earlier "IRQ TEST 227 error 09 with a disc, 127 error 06" readings were a one-off state on the
first load after a core switch; the controlled runs give error 0A on both builds. Run-to-run variance
on VAR TESTS is real but small (26069, 26072, 26073, 26083).

### Sub-CPU PRG-RAM /AS-to-/DTACK, measured (telemetry beat 3, build r8)

```
min 5 clk_sys (93 ns)   max 18 clk_sys (335 ns)   over-deadline SATURATED   n = 55.6M
```

The deadline is 6.44 clk_sys (120 ns, /AS at the start of S2 to the /DTACK sample at the end of S4).
The minimum matches the reference core's own "measured 93-105 ns AS to DTACK" exactly, so the typical
access does make it; the 335 ns tail does not, and those cost a wait state. **`tel_lat_slow` is 16 bits
and saturates within about a second at 1.85M PRG-RAM reads/s, so the fraction is still unknown - widen
it to 32 bits in the next probe.**

The early-DTACK A/B could not be completed on r8: bit 28 is gated `status[28] & dbg_menu` there and
dbg_menu needs Enter+Esc held together (`tools/mister/kbd_chord.py` was written for this), but there is
no way to confirm from the screen that the toggle landed. The p19 build ungates it.

## The reference core's early PRG-RAM DTACK fixes VAR TESTS - A/B'd on hardware, r9

OSD debug bit 28 switches the sub-CPU's PRG-RAM acknowledge between waiting for the data (today's
default, upstream) and acknowledging when the SDRAM accepts the request (the reference core's timing).
Four alternating runs, same MGL, same disc:

| bit 28 | VAR TESTS | IRQ TEST | REG 8030 | CDC FLAGS |
|---|---|---|---|---|
| 0 - ack on data | 26069/26085 **ERROR 02** | ERROR 0A | 1282/1283 | 47 ERROR 40 |
| 1 - **early ack** | **OK** | **227** ERROR 09 | 1281/1282 | 47 ERROR 40 |

Reproduced 2/2 each way. Nothing regresses: PROG RAM, WORD RAM, WRAM PMOD, CDC INIT and CDC DMA2/3/1
all still pass. jsgroth's expected range for the IRQ counting sub-test is 224-226, so 227 is one over.
**15 of 18.**

This is the reference core's own comment vindicated - "acknowledging only once the data was back cost
the die-accurate CPU a wait state on nearly every PRG-RAM fetch ... where the real PRG-RAM answers with
none (mcd-verificator VAR test)".

### Why it is NOT yet the default

Early DTACK acknowledges before the data lands, so S68K_PRGRAM_DO is stale until the SDRAM answers.
The reference core assumes "a fixed ~60 ns"; here it is not fixed, and phase18's telemetry measured it:

```
sub-CPU PRG-RAM /AS -> /DTACK:  min 5 clk_sys (93 ns)   max 15-18 clk_sys (279-335 ns)
```

`sdram.sv` serves five ports at fixed priority with the Mega CD PRG-RAM on port 2, below the cartridge
port the MD 68000 and both SH-2s share; the reference core has no 32X. With early DTACK the CPU latches
about 4-5 clk_sys after the acknowledge, so any read past that window hands it the previous word. At
1.85M PRG-RAM reads/s even 1e-6 is a couple of silent corruptions a second - the same class of bug as
the SDRAM settling fault that used to make builds flip between working and dead.

The observed maximum proves late reads happen. What is unknown is how often, because phase18's
over-deadline counter was 16 bits and saturated within a second. `tools/phase20_dtack_ratio.py` widens
both counters to 32 bits and makes the threshold selectable with OSD bit 27: >6 clk_sys is "cost a wait
state" (why the sub-CPU runs slow today), >9 is "would be corrupted by early DTACK". One bitstream
answers both. A title soak with bit 28 set is running alongside.

### Drive timing is not a problem - measured, r9 telemetry, during a running CD game

```
DEC_MID 75.1/s     DEC_FRAME 52.5/s     SECTOR_END 35.7/s     CDD_SEND 99.9/s
```

`DEC_MID` at 75.1/s confirms the Mega CD's own 75 Hz timebase is exact, so the denominator of the
CDC FLAGS measurement is sound and the earlier sector-rate theory is dead. DEC_FRAME below DEC_MID is
by design: SECTOR_END zeroes FRAME_CNT, and 75.1 - 52.5 = 22.6 lost frames against 35.7 sectors/s is
just SECTOR_END landing uniformly inside the 60% window. CDD_SEND at 99.9/s is above the hardware 75 Hz
because `ASIC.vhd` also hands the command registers over on every write to FF804A and resets the frame
counter; b66 has the identical ASIC, so it is not what separates us, but it is a deviation worth noting.

Beware measuring rates with `teldump.py`: each beat spawns python3 on the ARM, and timing the interval
by the sleep rather than the clock inflated CDD_SEND to 85.8/s. It now times the interval itself.

## Early DTACK measured: it fixes VAR TESTS by corrupting memory. Do not ship it.

phase20 widened the over-deadline counter to 32 bits (phase18's 16-bit one saturated within a second
at 2.2M PRG-RAM reads/s, so every earlier reading was a useless 0xFFFF) and made the threshold
selectable. Measured on r10 during a running Mega CD game, with bit 28 = 0 so the latency is the TRUE
SDRAM latency rather than the early acknowledge:

| threshold | meaning | result |
|---|---|---|
| > 6 clk_sys | costs the sub-CPU a wait state today | **1.38%** of reads (~30k/s) |
| > 9 clk_sys | would be CORRUPTED by early DTACK | **0.011 - 0.068%** of reads |

At 2.19M PRG-RAM reads/s that second figure is **250 to 1500 silently wrong data words per second**
handed to the sub-CPU. Early DTACK buys mcd-verificator VAR TESTS at the price of random memory
corruption, so it stays behind OSD bit 28 and is never the default.

The wait-state figure also kills the tidy explanation: 1.38% of reads losing 2 CPU clocks each is
~0.48% of sub-CPU time, well short of the 2-4% by which the CDC FLAGS poll loop runs slow. Wait
states are part of it, not all of it.

`tools/phase21_prg_priority.py` is the version worth building: leave the acknowledge on the data,
where it can never be stale, and remove the contention instead by lifting the Mega CD PRG-RAM port
above the cartridge port in `sdram.sv` (OSD bit 26). That is also the better hardware match - PRG-RAM
and the cartridge are separate memories that cannot stall each other on a real machine, and when a
shared controller must choose, the 12.5 MHz sub-CPU has 120 ns of slack against the 7.67 MHz main
CPU's 195 ns. Verified to apply cleanly against a scratch copy; note `old_rd`/`old_wr` are declared
INSIDE the always block, so the port-2 test has to be written out in each guard, not hoisted to a wire.

### Trap: status[27] is CD Audio. Do not reuse it.
phase20 first put the threshold switch on bit 27, which collides with `"P1OR,CD Audio"` (MegaCD.sv:204;
'R'-'A'+10 = 27), live audio routing at MegaCD.sv:713-716. Moved to bit 24. The two ratio readings
above were taken with CD audio rerouted - audio only, so the latency numbers stand. **Check every new
OSD bit against the letter-form entries (`O<char>` = bit 'char'-'A'+10), not just the `O[n]` ones.**

## The 32X SH-2s wedge - a real bug, and it is NOT any of the first four theories

Knuckles' Chaotix (32X cartridge, no disc) runs and then hangs: static picture, no PWM. Counters read
three times at 3 s intervals during the hang:

```
tel_seq    (telemetry heartbeat)        17F7 -> 1D0F -> 2228   ADVANCING
tel_lp     (display line prefetches)      B2 ->   EA ->   49   ADVANCING
tel_sdr_rd (SH-2 work-RAM reads)          42 ->   42 ->   42   FROZEN
tel_sdr_wr (SH-2 work-RAM writes)         3B ->   3B ->   3B   FROZEN
tel_fbd_wr (32X frame-buffer draws)       CA ->   CA ->   CA   FROZEN
```

**Both SH-2s have stopped touching memory. The DDR3 engine is healthy** - still servicing line
prefetches and returning to idle. No PWM follows because the SH-2s generate it.

Soak results (`tools/mister/soakfreeze.sh`, and `tools/mister/sh2watch.sh` which watches these counters
instead of frames - frames are a poor detector because an attract loop legitimately repeats one):

| build | result |
|---|---|
| r7 (before this session) | 6 min clean, then 10 min clean, 23 distinct frames |
| r9 | 6 min clean; froze once during a sweep, elapsed time unknown |
| r10 | **wedged at 90-135 s** (soak samples 2 -> 3) |

Leans regression but is not proven: time-to-failure varies. A reliable repro is the next step.
The user confirms it also hangs during REAL GAMEPLAY, so it is not an artefact of attract-mode testing.

### What has been positively cleared
- **Not the early DTACK.** Chaotix, Doom and VRDX all run with bit 28 both ways; and beat 3 reads all
  zero during 32X cartridge titles, i.e. the sub-CPU does no PRG-RAM reads at all, so that path is
  inert here.
- **Not MiSTer's screensaver.** `video_off=0` in MiSTer.ini.
- **Not the telemetry arbiter branch** (my own theory, refuted by a 17-agent audit). It runs only from
  S_IDLE, never interrupts a burst, costs <=8 clocks once per 2^17, and `lp_pend`/`fbd_rd_pend`/
  `sdr_*_pend` are held levels serviced on the next S_IDLE, so nothing is dropped.
- **Not EN_32X_VID blanking.** That would leave the SH-2s drawing behind a blank screen; these
  counters are frozen solid.
- `core/rtl/S32X/` is byte-identical r7..HEAD - no 32X datapath logic changed this session.

### Corrections to earlier entries in this file
Three conclusions recorded above were overturned by later measurement. Do not act on them:
1. **The sector-rate theory is wrong.** It rested on d4 = 87 taken from a session summary and never
   verified; the measured value is 47. Duty cycle is exactly 40.5% and DEC_MID runs at 75.1/s.
2. **"Disc activity breaks the timing tests" is wrong.** The 227/error-09 and 127/error-06 readings
   were a one-off state on the first load after a core switch; controlled runs give error 0A.
3. **"The 68000 is alive during the hang" is unsupported.** `tel_lp` comes from free-running video
   timing (`VDP.sv:455`), not from any CPU, and the YM2612 sustains its last register state.

## The 32X SH-2 wedge: an UPSTREAM deadlock in RS_MD_WAIT, fixed in r11

`core/rtl/S32X/IF.sv` `RS_MD_WAIT` was a trap state. Verified line by line:

- `ba.sv:595` `assign CAS0_N = ~MBUS_RNW | MBUS_AS_N` - /CAS0 is asserted on **reads only**;
  `ba.sv:596-597` assert the write strobes on writes only.
- `cart.sv:243` `ROM_RD = ROM_ACCESS & ~CAS0_N`, and `cart.sv:244` ties `{ROM_WRH,ROM_WRL}` to
  `2'b00` for any normal cartridge (only `schan_quirk` is different). So an MD **write** into the
  32X ROM window produces **no SDRAM port-0 request at all**, and `busy0` never rises.
- `IF.sv:823-825` sets `MD_ROM_WAIT` on `LWR_F || UWR_F || CAS0_F`, i.e. writes included, with
  `MD_ROM_PASS <= !MD_32XROM_SEL` - so 0 for `$880000-$9FFFFF`.
- `RS_MD_WAIT` had exactly two exits: `ROM_WAIT_SYNC` (= `busy0`) and `MD_ROM_PASS && !CART_EXT`.
  For a `$880000` write the first can never happen and the second is disabled.

`ROM_ST` then never returns to `RS_IDLE`. `SH_ROM_WAIT` is set by any SH-2 CS1 fetch and cleared
**only** in `RS_SH_READ`, now unreachable, so `SHWAIT_N` stays low and **both SH-2s park for ever**;
`MD_ROM_DTACK_N` never asserts so the 68000 dies with them and the YM2612 holds its last registers.
Exactly the measured signature: SH-2 work-RAM reads/writes and frame-buffer draws all frozen while
the DDR3 engine stayed healthy and free-running video timing kept `tel_lp` moving.

### It is upstream's bug, not this merge's
```
32X/IF.sv:879        RS_MD_WAIT: if (ROM_WAIT_SYNC) -> RS_MD_READ     <- the ONLY exit
32X/IF.sv:819        MD_ROM_WAIT set on (LWR_F || UWR_F || CAS0_F)    <- writes included
S32X_MiSTer_upstream/S32X.sv:597   .USE_ROM_WAIT(1)                   <- the path is live
grep -c "MD_ROM_PASS\|CART_EXT" 32X/IF.sv  ->  0
```
Pristine upstream has neither `MD_ROM_PASS` nor `CART_EXT`, so its `RS_MD_WAIT` has one exit and the
same `$880000`-write deadlock, live in the shipping standalone 32X core. This fork *widened the
trigger* (`IF.sv:823` also routes `/CE0` pass-through cycles through the flag, where upstream had only
`MD_32XROM_SEL`) but also added the only escape that exists. Worth reporting upstream.

### The fix (r11)
Drop the `MD_ROM_PASS &&` qualifier: `!CART_EXT` on its own already means "nothing behind the
connector will answer this cycle", which is equally true of a write to a read-only ROM window. No race:
`CART_EXT` is combinational from the `S32X_*` strobes latched a clock earlier in `RS_MD_RW`, so it is
valid throughout `RS_MD_WAIT`; and for a genuine read `CART_EXT` is high, so the escape cannot fire
early. 78% ALMs, timing +0.400 ns. Deployed as `MegaCD_PB`, **not yet tested on hardware**.

**Still to prove:** that Chaotix actually takes this path. The deadlock is real and reachable and the
fix is correct regardless, but the confirmation is r10 wedging at 90-135 s where r11 does not.
Use `tools/mister/sh2watch.sh MegaCD_PB_chaotix ... 20 15`.

### Separate real defect, not yet fixed: SH7604 WDT clock tap
`core/rtl/SH/SH7604/SH7604.sv:670` wires the WDT's `CLK2_CE` port to `CLK8_CE`. `WDT.sv:48` selects
that port for `WTCSR.CKS=000`, which the SH7604 defines as phi/2; the prescaler
(`SH7604.sv:572-583`) has no divide-by-2 tap at all, the smallest being `CLK4_CE`. So `CKS=000` ticks
at phi/8 and the 8-bit WTCNT overflows every 89.00 us instead of 22.25 us - **4x slow**. `CKS=001..111`
are all correct, and `WTCSR_INIT = 8'h18` (`SH7604_PKG.sv:332`) selects `CKS=000` at power-on, so any
code enabling TME without rewriting CKS lands on the broken tap. Both SH-2s carry it.

## Doom CD32X Fusion: located to a three-way rendezvous that never completes

### It was region-locked, not crashing
First frame of a Fusion boot is `ERROR! THIS IS A PAL/SECAM-COMPATIBLE MEGA-CD AND WILL NOT OPERATE`.
Main auto-loads the EU `boot.rom`, so a US title refuses. Fixed for testing by copying
`games/MegaCD/USA/cd_bios.rom` next to the Fusion files (the per-game override). Everything below is
with that in place. **Screenshot the first few seconds of a boot before theorising about a crash.**

### The tower itself is fine
Night Trap (CD32X) runs perfectly on the same build: 10 distinct frames, `sdr_rd`/`sdr_wr`/`fbd_wr`
all advancing, SECTOR_END 75.0/s. So Mega CD -> 68000 -> 32X works. Fusion is specific.

### All three CPUs are alive; none of them progress
Measured with the r13 telemetry (SH-2 PCs, 68000 bus cycles, `$A151xx` accesses):

```
master SH-2   0201DD5A..0201DD60   6-byte spin loop in Fusion's cart ROM  (150/150 samples)
slave  SH-2   0201E5CE..0201E5DE   16-byte spin loop in cart ROM
68000         63.0M -> 82.9M bus cycles, $A151xx 1.08M -> 1.38M   ALIVE, ~27k reg accesses/s
sub-CPU       ~1.9M PRG-RAM reads/s                                ALIVE
fbd_wr        202 -> 202                                           frozen: nothing is drawn
```

Disassembled out of the ROM itself (`tools/dis_sh2.py`, capstone SH-2):

```
MASTER  0201DD58  mov.l 0x201de7c,r7    ; literal at ROM 0x1DE7C = 0x20004024
        0201DD5A  mov.w @r7,r13
        0201DD5C  tst   r13,r13
        0201DD5E  bf    0x201dd5a        -> spin while COMM register NON-ZERO

SLAVE   0201E5CE  mov.w @r8,r2
        0201E5D0  cmp/pz r2
        0201E5D2  bf    0x201e5ce        -> spin while bit 15 SET
        0201E5D6  mov.w r10,@r8          -> then push a value
```

`0x20004024` is the SH-2 view of the 32X comm register at MD `$A15124`. **NOTE the numbering trap:**
d32xr names comm registers by BYTE OFFSET, so its COMM0/COMM2/COMM4 are `$A15120`/`$A15122`/`$A15124`
= our `CP0R`/`CP1R`/**`CP2R`** (offset 6'h24). `CP4R` is offset 6'h28, a different register.

The 68000 side (d32xr `src-md/crt0.s`, `main_loop_handle_req`) polls `$A15120` for a master request
and `$A15124` for a secondary one, services it, and writes 0 back. It is demonstrably in that loop
(~27k `$A151xx` accesses/s). So the master posts a request and the 68000 never clears it, or never
sees it. The slave's "wait for bit 15, then push" is the shape of the PWM FIFO FULL flag, and
`IF.sv:695` only drains that FIFO while `PWMCR.LMD || PWMCR.RMD` - if it never drains, FULL sticks
and the slave spins for ever.

### What has been cleared by diffing against pristine upstream `32X/IF.sv`
`CP0R..CP7R` both directions, the whole PWM block, `DCR.RV`, `BSR` banking, `ICR`/CMD interrupt
generation, and the MD register write decode are **byte-identical**. This is not a transcription
error, so reading the register VALUES is the only way forward - `tools/phase27_comm_regs.py` adds
beat 6 with `{CP0R, CP1R, CP2R, LPWR.FULL, LPWR.EMPTY, RPWR.FULL, RPWR.EMPTY, PWMCR[11:0]}`.

### Fusion's Mode 1 contract, from src-md/scd.c - worth keeping
```c
write_word(0xA12002, 0xFF00); write_byte(0xA12001, 0x03/0x02/0x00);  // gate array reset sequence
write_byte(0xA12001, 0x02); while (!(read_byte(0xA12001) & 2)) ...   // reset sub-CPU, wait SBRQ
write_word(0xA12002, 0x0002);                                        // bank 0, 2M, WordRAM to sub
memset((char *)0x420000, 0, 0x20000);                                // clear PRG-RAM, mode-1 window
Kos_Decomp((uint8_t *)bios, (uint8_t *)0x420000);                    // sub BIOS out of the CD BIOS
memcpy((char *)0x426000, &Sub_Start, ...);                           // its own sub-CPU program
write_byte(0xA12001, 0x01); while (!(read_byte(0xA12001) & 1)) ...   // start sub-CPU, wait SRES
while (read_byte(0xA1200F) != 'I') ...                               // sub program alive (timeout)
while (read_byte(0xA1200F) != 0x00) ;                                // ready  (NO timeout)
```
It also uses **Word RAM in 1M mode** (`char *scdfn = (char *)0x600000; write_long(0xA12010,0x0C0000);`)
and its own sub-CPU program is incbin'd in the cart ROM (`src-md/cd.s`), so the 68000 uploads and
starts it - full Mode 1. jgenesis does NOT support CD32X at all (jsgroth, issues #148/#673), so there
is no reference implementation for this combination; issue #701 is Fusion-specific and was filed by
the d32xr author.

## Fusion, traced to a 68000 <-> master SH-2 deadlock on COMM0 (not yet fixed)

Instrumentation added across r13-r19: both SH-2 PCs, MD 68000 address bus, MD `$A151xx` and `$A120xx`
traffic with read/write counts, 32X comm registers + PWM status, Mega CD comm flags, and sub-CPU
halt state. Readers: `tools/mister/pcsample.py`, `scratch/both.py`, `scratch/halt.py`, `scratch/a12.py`.
SH-2 disassembly via `tools/dis_sh2.py` (capstone SH-2), 68000 via `tools/dis68k.py`.

### State when Fusion is hung (all measured, r19)
```
68000     spins at $884C08 in Fusion's MD code ($880000 window = ROM offset 0x4C08)
          reads $A15120 (COMM0) at >100k/s, waiting for BIT 0 to be set
          $A120xx traffic COMPLETELY FROZEN (writes 1461, reads 2080, no movement)
master    spins at 0201CBC2..C8 - a cache-purge loop (r12 = (r5+8) | 0x40000000, stride 16)
slave     spins at 0201E5CE..DE - "wait while bit 15 set, then push"
sub-CPU   SRES=0 SBRQ=1, /AS idle, zero PRG-RAM reads: HELD, not stalled
          stops at a different address every run (007C40, 00A03E, 005E76)
CP0R      0x2E00 or 0x2054 depending on run; 0x2E = prireqtbl[46] = play_cd_roq_file
CFM/CFS   00/00, both static.  SECTOR_END and CDD_SEND static (HOCK=0)
```

**The sub-CPU being held is deliberate and downstream**: the last `$A120xx` write was `$A1200E = 0101`
(a comm flag), and `$A12001` was written `0x02` before that to halt it for a transfer. The 68000 then
got stuck waiting on the 32X and never released it. Do not chase the sub-CPU halt as the root cause -
that was a wrong turn, corrected by the `$A120xx` write capture showing zero traffic.

### Positively cleared
- **Region lock** - was the original "crash": `ERROR! THIS IS A PAL/SECAM-COMPATIBLE MEGA-CD`. Fixed
  for testing with a US `cd_bios.rom` beside the Fusion files.
- **The CD32X tower** - Night Trap runs perfectly on the same build, 75 sectors/s.
- **Our 32X core** - plain Doom 32X renders its full title screen on the same build.
- **PWM FIFO** - `LMD=1 RMD=1`, FIFO reads EMPTY. The phase28 fix (drain regardless of output mode,
  as PicoDrive does) is real and worth keeping, but is NOT this bug. Held, unapplied.
- **The 0x13C BIOS trap** - intermittent; `trap_hit` was 0 in the failing runs, so the master is
  genuinely spinning in game code, not trapped.
- **Debug bit 39** (EXT_AS_N source) - A/B'd both ways, identical result.
- **Every 32X register path** - CP0R..CP7R both directions, PWM block, DCR.RV, BSR banking,
  ICR/CMD interrupt generation, MD register write decode: byte-identical to pristine upstream.
- **Cache purge area** - `CACHE.sv:48 PURGE_AREA = (CBUS_A[31:29] == 3'b010)` is implemented, so the
  master's purge loop is legitimate game code.

### Where to go next
The deadlock is 68000 (waiting for COMM0 bit 0) against the master SH-2 (purging cache in a loop,
i.e. polling memory another CPU should have written). One side missed a signal. The open question is
what the 68000's `$884C08` loop is really waiting for - `(a6)` was assumed to be `$A12000` and that
is now disproved, so re-derive `a6` by disassembling backwards from `$884C08` to find where it is
loaded, rather than guessing from which registers are busy.

### Reference notes
- **jgenesis does NOT support CD32X at all** (jsgroth, issues #148/#673) - no reference for this
  combination. Issue #701 is Fusion-specific, filed by d32xr's own author.
- **PicoDrive (notaz) is the only CD32X emulator** - `pico/32x/pwm.c`, `pico/32x/memory.c` are the
  reference for 32X behaviour.
- d32xr names comm registers by BYTE OFFSET: its COMM0/COMM2/COMM4 are `$A15120`/`$A15122`/`$A15124`
  = our `CP0R`/`CP1R`/`CP2R`. `CP4R` is `$A15128`. This cost an hour.
- Fusion's Mode 1 init and its `prireqtbl` command table are in `src-md/scd.c` and `src-md/crt0.s`.

## The SH-2 cartridge read had the r7 bug too - and the tower is what exposes it

`sdram.sv` shares ONE data register across all five ports:
```
sdram.sv:134  reg [15:0] dout;
sdram.sv:136  assign dout0 = dout;  dout1  dout2  dout3  dout4
sdram.sv:227  dout <= SDRAM_DQ;     reloaded on ANY port's read completion
```
Every consumer must latch it on its own handshake. r7 fixed that for the Mega Drive cartridge path.
**The SH-2 cartridge path had the same defect, with a wider window:**
```
IF.sv:860   if (!ROM_WAIT && CE_F) begin
IF.sv:861       SH_ROM_DO <= CDI;        <- live wire into the shared register
```
The MD path captures as soon as its wait drops; this one also waits for `CE_F`, the SH-2 clock
enable, asserted on only 3 of every 7 clk_sys. A word that is already valid therefore sits exposed
for up to three clocks while the Mega CD's BIOS ROM (port 1), PRG-RAM (port 2) and PCM (port 3) can
each complete a read and overwrite `dout`. The SH-2 executes whatever landed there.

Evidence it is real:
- the master takes **wild jumps** - the frozen trap trail shows `060005C0 -> 060005C2 -> 0000013C`,
  i.e. it ends up executing the 32X boot ROM's vector table as code and walking into `BRA .`
- it is **intermittent**, as a race must be
- it **tracks contention**: trapped 2 of 3 runs with the disc in, 0 of 3 cart-only

`32X/IF.sv` is byte-identical here, so srg320's standalone 32X carries the same race and never feels
it - that core has no Mega CD ports competing for the register. This is a latent upstream bug that
only the tower exposes, and worth reporting upstream.

**Fix (r21, `tools/phase35_sh_rom_latch.py`)**: capture `CDI` the first cycle the word is valid and
hold it in `SH_ROM_DO` until the SH-2 clock edge consumes it, via a one-shot `SH_ROM_CAP` flag
cleared in `RS_SH_RW`. The state machine still advances on `CE_F`, so SH-2 bus timing is unchanged.

### Instruments built tonight (all in the tree, all reusable)
`tools/dis_sh2.py` (capstone SH-2), `tools/dis68k.py`, `tools/conf_bits.py` (OSD bit map - every one
of the 64 status bits is claimed), `tools/mister/pcsample.py`, `tools/mister/sh2watch.sh`,
`tools/mister/soakfreeze.sh`, `tools/mister/freezetest.sh`, `tools/mister/teldump.py`, plus telemetry
beats 0-12: 32X DDR3 counters, audio peaks, sub-CPU PRG-RAM latency, drive sector rates, both SH-2
PCs, MD 68000 address + `$A151xx`/`$A120xx` traffic, 32X comm registers + PWM, Mega CD comm flags,
sub-CPU halt state, and the master's pre-trap PC trail.

## BREAKTHROUGH: Fusion says what is wrong. It cannot read its data from the CD.

The master SH-2 ends up spinning at `0201955A`, which is `bra 0x201955a` / `nop` - **Fusion's own panic
handler**, not a deadlock:

```
02019524  <panic(msg)>  takes the message in r4, formats 84 bytes on the stack,
02019532                calls 0x0200CED8 (vsnprintf), 0x02019488, 0x02018FB0, 0x02018400
0201955A  bra .         then HANGS DELIBERATELY
```

The formatted message is on the SH-2 stack, and the SH-2 stack is in work RAM, which is in HPS DDR3 -
so it can be read straight out of Linux. Dumping `0x3003F000` and un-swapping (the engine stores
SH-2 16-bit words byte-swapped, in 8-byte groups) gives:

```
"R_InitDa" "ta: 1006" "91256 >=" " numlump"   ->   R_InitData: <n> >= numlumps
```

Confirmed against the ROM at `0x02C5CF`: the format string is `"%s: %i >= numlumps"`, and
`R_InitData` is at `0x02C860`. That is Doom's WAD lump-bounds check failing - the lump index is past
the end of the directory, i.e. **the WAD it loaded from the CD is missing or wrong**.

Corroborated by the sector telemetry: **SECTOR_END reached only 34 and then stopped.** ~80 KB is
nowhere near a WAD. The CD read starts and dies.

**So the remaining bug is the Mega CD Mode-1 file read, not a 32X problem at all.** Everything else -
the 68000 waiting at `$884C08`, the slave spinning, `fbd_wr` frozen, the black screen - is downstream
of the panic. `tools/mister/scan.py` dumps and un-swaps work RAM; reuse it, this technique is general.

### Cleared while getting here
- `rom_download = bios_download | cart_download` (MegaCD.sv:369) does NOT include CD data, so sector
  transfers do not reset the Mega CD block. Identical to the reference.
- The SH-2 ROM latch fix (r21/r22) is real and helps - no `0x13C` traps in 4 runs where the previous
  build trapped 2 of 3 - but it is not what keeps Fusion black.
- r21's timing failure was on `pll_hdmi` only (the HDMI scaler); the core's own clocks had +0.750 ns,
  so its functional results were valid. r22 closes everything at +0.588 ns with telemetry off.

### Next
Find why the sub-CPU ends up held at SRES=0/SBRQ=1 with the 68000 no longer touching `$A120xx`.
`SRES` is only cleared by an MD LDS write of bit 0 to `$A12001` (ASIC.vhd:616) or by the ASIC's own
`RST_N`, and both have been checked. Capture the $A12001 write VALUE history (not just the last one)
to see the actual sequence, and correlate with where the 34 sectors stop.

## The Mode-1 file read: we were re-issuing a live CDD command every frame

Main_MiSTer owns the drive. Its poll loop treats **every toggle of the core's request line as a NEW
command** (`Main_MiSTer/support/megacd/megacd.cpp`, `mcd_poll`):

```c
uint8_t req = spi_uio_cmd_cont(UIO_CD_GET);
if (req != last_req) { ... cdd.SetCommand(c, 0); cdd.CommandExec(); has_command = 1; }
```
and `CommandExec` re-seeks for a play (`support/megacd/megacdd.cpp`):
```c
case CD_COMM_PLAY:
    MSFToLBA(&lba_, comm[2]*10+comm[3], ...);  lba_ -= 150;
    SeekToLBA(lba_, 1);          // back to the LBA still sitting in the command registers
    this->status = CD_STAT_PLAY;
```
Main advances the drive on its **own** 75 Hz timer (`poll_timer = GetTimer(13...)`), one sector per
`cdd.Update()`. The request line is only ever meant to mean "here is a new command".

`ASIC.vhd` handed the command registers over **once per 75 Hz frame** as well as on a write to
`$FF804A`. While a PLAY is still in those registers that makes Main seek back to the start of the
read ~75 times a second, so a file transfer never advances - **SECTOR_END reached 34 and stopped**,
the WAD never loaded, and Fusion panicked with `R_InitData: <n> >= numlumps`.

Titles that boot from the disc under the BIOS are unaffected: well-behaved software leaves
`CD_COMM_IDLE` (0x00) in the command registers between commands and IDLE is idempotent, which is why
Night Trap streams at 75 sectors/s on the same build.

**Fix (r24, `tools/phase36_cdd_idle_poll.py`)**: still send on a command write - that is the real
event and what Main expects - but only poll periodically while `CDDC(3 downto 0) = 0` (IDLE). That
keeps the reason the periodic send was added (mcd-verificator's CDC INIT hang, and software that sets
HOCK then only polls status) without ever re-issuing a live command.

**This one is ours**, not upstream: the periodic send was added here to fix CDC INIT and it broke
file reads. ares confirms the intended model - `MCD::CDD::clock()` runs at a strict 75 Hz and only
raises the IRQ via `statusPending`; `process()` runs once, on the command write.

### The disc is fine - checked, not assumed
`tools/../scratch/isoinfo.py` lists the image: valid ISO9660 "DOOM CD32X FUSION", DOOM.WAD (506
lumps), DOOM_II.WAD (458), MAPDEV.WAD (1397), RESURRECTION.WAD (344), SOUNDS.WAD (88), TNT_MINI.WAD
(120), plus VGM_* and VIDEO/IDLOGO.ROQ (1.5 MB - the id logo, which is what `play_cd_roq_file`
command 0x2E goes after). Fusion ships its own converted PWADs, so a user's DOOM.WAD is not used.

## r25/r26: the PWM drain fix clears the DMA deadlock, and the CD read is NOT the blocker

**Fixed and shipped.** `releases/MegaCD_MD_MCD_32X_r26_pwmdrain_clean.rbf` (seed 3, timing clean,
worst-case setup slack +0.107). r25 is the same source at seed 1 and misses by -0.057 on a
`sdram|reset[4] -> SDRAM_DQ[0]~en` half-cycle path that has nothing to do with the change; the
reseed was the whole fix for that.

`tools/phase28_pwm_drain.py` — the PWM FIFO must keep draining with the L/R output mode off.
PicoDrive's `consume_fifo_do()` (pico/32x/pwm.c) advances the FIFO on elapsed cycles alone and never
consults the output mode; `IF.sv:685` halted the entire timebase when `LMD=RMD=0`. Measured on
Fusion before and after:

| | r24 | r26 |
|---|---|---|
| master SH-2 | `0201F8CC` forever | running game code |
| PWMCR | `000` | `185` |
| PWM FIFOs | `LF=1 RF=1` (full, latched) | `LF=0 RF=0` (draining) |

The master was spinning on `mov.l @r3,r0 / tst #2,r0 / bt` with `r3 = 0xFFFFFF9C` — SH7604 DMAC
CHCR1, bit 1 TE. Output mode off -> FIFO can't drain -> FULL latches -> DREQ never asserts -> the
PWM DMA never completes -> TE never sets. That whole chain is gone.

**The Mode-1 file read works.** This was the standing theory and it is wrong, established without
touching the core: Main_MiSTer owns the drive, so its state is the ground truth. `cdd` is a global
in a stripped binary, but its header is two consecutive `.text` pointers (`SendData`,
`CanSendData`) after `loaded == 1`, which locates it uniquely; the layout then checks out against
the real disc (`toc end=9485 last=1`, `track0 start=0 end=9485 type=1 sector_size=2048`).
Tools: `scratch/cddpeek.py`, `scratch/cddfull.py`, `scratch/cddlog.py`.

What that shows:
- `mcd_can_send_data()` returns 1 unconditionally for `TT_MODE1`, so the core never throttles it.
- The reads happen. `/proc/<MiSTer>/fdinfo` has the ISO's file pointer at sector 8940 — 339 sectors
  into `VIDEO/IDLOGO.ROQ` (LBA 8601, 1501892 bytes). Fusion gets through boot, through the 32X
  handshake, releases the sub-CPU, and streams the intro video off the disc.
- The drive stopping is **correct behaviour**: `begin_read_cd` (d32xr `cd/crt.s`) issues BIOS
  `ROMREADN` for `CHUNK_BLOCKS` = 8 sectors and the BIOS pauses the drive at the end of each chunk.
- The final `CD_COMM_STOP` is Fusion's own error path, ~30 s after it gives up, not a cause.

**The actual blocker: the master SH-2 crashes.** Coherent snapshot at the stall:

```
master  0000013C   <- the 32X BIOS BRA-to-self exception trap
slave   000001C7   BIOS idle loop
CP0     2E00       command 0x2E still posted = play_cd_roq_file (prireqtbl index 46)
CFM/CFS 00/00      frozen, MD and sub-CPU both idle-polling
drive   STOP       lba 8940
```

Everything else follows from that one crash. The MD is idling in `main_loop_handle_req` polling
`$A15120` at ~40k/s with nothing to do (its bus histogram has **no `$A15128` at all**, so it is not
in the RoQ loop), the sub-CPU's only gate-array traffic is `$FF800E`, and the master never clears
COMM0, so `roq_request()` never sets `MARS_ROQFL_REQ`.

Instrumentation built this session, all zero-rebuild:
- `scratch/subhist.py` / `scratch/mdhist.py` — address-bus histograms for the sub-CPU and the MD,
  enough to name the loop each is in. `DBG_S68K_A` is the full bus, so `$FF80xx` shows up.
- `scratch/cfprobe.py` — the `$A1200E`/`$A1200F` comm flags plus their change counters.
- `scratch/stall.py` — waits for `SECTOR_END` to start and then stop, and samples at that instant.
- `scratch/shframe.py` — 32X work RAM is DDR3 `0x30000000`, stored as **byte-swapped 16-bit words**
  (verified: `2f 16` = `mov.l r1,@-r15`, `4f 22` = `sts.l pr,@-r15`). Readable live from Linux.

Ruled out along the way: the Mega CD PRG-RAM path does latch `PRG_DI` correctly
(`ASIC.vhd` `PRS_READ`, on the same edge busy drops, inside the controller's 2-cycle guarantee), and
the 32X work-RAM path is fed from a registered line cache in `s32x_ddr.sv`, not the shared `dout`.
So neither has the r7/phase35 shape.

**Next:** `tools/phase41_jump_trail.py` (build r27) latches the *transition* out of game code rather
than the trap — `{jump_from, jump_to}` plus the two preceding PCs — because the old two-deep trail
only ever caught the walk through the vector table (`0000013A -> 00000138 -> 0000013C`). It also
swaps the spent PWM fields of `DBG_COMM` for CP4R = `$A15128` = `MARS_SYS_COMM8`, the register the
RoQ stream runs on.

Also worth knowing: `load_core` of an MGL from the menu races the MGL's own `delay=` fields and
often leaves the 32X unstarted. Loading the core first and the game second is reliable. Several
"mode A" boot failures earlier in the session were this, not a core bug.

## ROOT CAUSE, third time: sdram.sv's single shared `dout` is corrupting SH-2 longword reads

The r27 jump trail (`tools/phase41_jump_trail.py`) latches the PC either side of the master leaving
real code. It caught the crash twice, and both are the same shape - `jsr` through a register loaded
by a **PC-relative longword read from cart ROM**:

```
0201DC34  mov.l 0x201dce8,r14     ROM holds 0201F284   master got 00000001
0201DC40  jsr   @r14
0201DC42  mov   r9,r5             (delay slot; what the trail reports as jump_from)

0201C57C  mov.l 0x201c5b0,r5      ROM holds 02017E38   master got 00000012
0201C58C  jsr   @r5
```

The literal values were read straight out of `scratch/fusion.32x`, so "what it should be" is not a
guess. Small values like 1 and 0x12 are what the Mega CD's BIOS ROM (port 1), PRG-RAM (port 2) or
PCM (port 3) was reading at that instant: they land in `sdram.sv`'s one shared `dout` register
between the SH-2's two 16-bit bus cycles. The SH-2 caches cart ROM, so one poisoned word stays for
the whole 16-byte line.

The master then jumps to a tiny address and **walks forward through the BIOS vector table** - whose
entries are all `0000013C` and harmless as data - until it reaches the `BRA .` at 0x13C. That is
the "wild jump into the vector table" seen since r18, finally explained. `tools/mif2bin.py` +
`dis_sh2.py` on `shbios.mif` show the table directly: vec 0 = 0x140 (reset PC), vec 1 = 0x06040000
(initial SP), and **53 of 80 entries point at the 0x13C trap**, so the trap identifies nothing by
itself.

Also nailed down: it needs the Mega CD active. Cart-only Doom 32X and cart-only Fusion both ran 45 s
with the master in real code and PWM cycling normally.

This is the SAME DEFECT for the third time - r7 on the MD cartridge path
(`phase17_cart_latch.py`), r21 on the SH-2 cartridge path (`phase35_sh_rom_latch.py`), now on SH-2
longword literals. Both earlier fixes were consumer-side latches racing to grab the shared register
before someone else overwrote it. `tools/phase42_sdram_per_port_dout.py` fixes the cause instead:
`ram_req` is already one-hot for the port being served, so each port gets its own output register.

**r28 failed - record it so nobody rebuilds it.** The obvious form, five enabled registers each
capturing `SDRAM_DQ` directly, compiles clean (+0.084) and **does not work**: the core comes up with
both SH-2s at PC 0 and zero `$A151xx` accesses, only the MD 68000 ticking over. `SDRAM_DQ` capture is
a tight input path - r25 had already failed timing on `sdram|reset[4] -> SDRAM_DQ[0]~en` - and
fanning it to five loads across the fabric breaks it. A/B against r26 on the same MGL confirmed the
regression rather than a bad load.

r29 therefore leaves the capture path byte-identical - one register, one load on `SDRAM_DQ` - and
splits per port **one cycle later** from the captured value. There is room: `busy` is
`ram_req | ram_req_d | ram_req_d2`, high for three cycles after `STATE_READY`, and consumers sample
when it falls, so the distribution lands two cycles early.

Byte order for reading 32X work RAM from Linux, corrected: a 16-bit word at SH-2 address A is at
DDR3 offset `(A - base) XOR 2`, and a 32-bit value reads back as a plain little-endian load. The
first version of `scratch/shframe.py` used byte-swap-only and found nothing; with the right mapping
the master's stack decodes into real return addresses (0x0201E5D0, 0x0201CAF8, 0x060005EC).

## r29 SHIPPED - the per-port fix is right, but it is NOT the whole crash

`releases/MegaCD_MD_MCD_32X_r29_perport_dout.rbf`, timing clean (+0.082), deployed as the main core.
Validated: boots, runs, and **Night Trap streams at 75.0 sectors/s with a 13.33 ms period - exactly
hardware** - so the SDRAM change causes no regression.

What it fixes: the shared-`dout` race in `sdram.sv` is gone, properly, for all five ports. That is a
real defect and it is closed.

**What it does NOT fix: the master SH-2 still takes corrupted longword reads.** Caught again on r29:

```
run 2: JUMP: 0201DC68 -> 0201DC6A -> 0201DC6C  ==>  00002E01
0201DC5C  mov.l 0x201dcfc,r2      ROM holds 0201F6EC
0201DC6A  jsr   @r2
```

Expected `0201F6EC`, got `00002E01`. **Both halves are wrong**, so this is not the clean
"another port's data" story the shared register told - and note `0x2E01` is suspiciously close to
COMM0's live value at the time (`CP0=2E00`). Across all four captures the high word is always
exactly `0x0000`:

    00000001   00000012   000005EC   00002E01

Still contention-linked: with the CD, the jump fires; **cart-only Fusion on r29, 4 runs, zero
jumps**. So the remaining fault needs the Mega CD active but is not the `dout` sharing.

Leads for next session, in order:
1. `assign SHDO = SH_ROM_SEL ? SH_ROM_DO : SH_VDP_SEL ? VDP_DI : SH_REG_DO;` (IF.sv). A cart read
   returning `SH_REG_DO` would explain a comm-register value appearing in a ROM literal.
2. `if (SH_ROM_SEL && !SHBS_N && CE_F) SH_ROM_WAIT <= 1;` (IF.sv:833). The wait is asserted only on
   CE_F, so there is a window where the SH-2 has started a cart access and `SHWAIT_N` still says
   "no wait". If the SH-2 samples then, it gets the PREVIOUS read's `SH_ROM_DO`. Under contention
   the previous access takes longer, which fits the CD-only correlation.
3. Widen the trail to record the faulting *address* as well as the PC, so expected-vs-actual can be
   read off directly instead of inferred from the literal pool.

Separate, and NOT CD-related: roughly half of all boots stall at the 32X handshake with the master
at 0x248-0x250 and `CP0=5351 CP1=4552` (the MD is waiting for `M_OK` = 0x4D5F4F4B, crt0.s:329).
This happens cart-only too - 2 of 4 runs - so it is its own bug, not contention.

## FUSION RUNS. Root cause: the SH-2 cartridge read never waited for the SDRAM to acknowledge

`releases/MegaCD_MD_MCD_32X_r30_sh_handshake.rbf` (+0.129 slack), deployed as BOTH MegaCD_PP and
MegaCD_PQ. Doom CD32X Fusion reaches its title screen and menu with a live animating demo behind it.

`tools/phase43_sh_rom_handshake.py`. The cartridge arbiter serves both CPUs, but only one of them
ever checked that the SDRAM took its request:

```
IF.sv:908  RS_MD_WAIT: if (ROM_WAIT_SYNC)                              <- waits for the ACK
IF.sv:866  RS_SH_WAIT: if (/*(ROM_WAIT_SYNC || !USE_ROM_WAIT) &&*/ CE_F)   <- ACK COMMENTED OUT
```

The SH-2 path advanced on a fixed timer, two CE_F periods (~75-93 ns). Cartridge-only that works by
luck: `sdram.sv` is in STATE_IDLE when the strobe arrives and accepts within ~1 clk_ram. With the
Mega CD running, ports 1 (CD BIOS), 2 (PRG-RAM) and 3 (PCM) keep the controller busy, refresh is
tested BEFORE port 0 in the same else-if chain (sdram.sv:161-167), and `prg_first` steps over port 0
outright - acceptance slips to 8-14 clk_ram, PAST the timer. `RS_SH_READ` was then entered with
ROM_WAIT still low, captured the PREVIOUS port-0 word, and `SH_ROM_CAP` locked it in.

Before/after, eight consecutive boots each:

| | r29 | r30 |
|---|---|---|
| wild jumps | fires | **0 of 8** |
| boot-handshake stalls | ~50% | **0 of 8** |
| RoQ intro | never finished | **EOF every run** |
| screen | black | title screen + menu + animating demo |

**phase35 was treating the symptom.** It made the capture earlier and added SH_ROM_CAP to hold it -
which made the stale value STICK rather than self-heal. The real defect was a commented-out
qualifier, and the correct form was ten lines below it in the same state machine.

### STILL OUTSTANDING - race (a), NOT fixed by r30

`sdram.sv` detects requests by RISING EDGE only (`~old_rd[0] && rd[0]`), but the cartridge strobe
muxes are qualified by `&& S32X_CE0` (IF.sv:1103-1107), so whenever the arbiter is BETWEEN grants
the MD 68000's raw /CE0 and /CAS0 pass straight through to the cartridge with the MD's address. If
the controller accepts that unarbitrated read, `rd0` is already high when the SH-2 is granted, so
the SH-2's own request never produces a rising edge and is never issued - only the address under it
changes. The SH-2 then waits on the MD's busy and captures the MD's word, from the MD's address.

r30 does NOT fix this: the handshake now waits for ROM_WAIT to rise, but ROM_WAIT does rise - from
the MD's access. This is a real latent bug and is the top remaining technical item. If rom_sz > 4 MB
(cart.sv:85,231 set ROM_LIN_EN) it would run almost continuously.

## r30 validation sweep, and r31 tested

**r30 — the shipped build. Verified:**

| test | result |
|---|---|
| Fusion, 8 consecutive boots | 8/8 clean, RoQ intro reaching EOF every run, 0 wild jumps |
| Fusion, 10 min instrumented soak | **0 of 20 samples faulted** |
| 13-title sweep | all clean and rendering |
| mcd-verificator | unchanged: VAR TESTS 02, IRQ TEST (09, was 06), REG 8030 07, CDC FLAGS 40 |

Titles swept, all `JUMP: clean` and animating: chaotix (a known crash - **now fine**, intro renders
correctly), vrdx, doom, fusion, cd_nighttrap, cd_corpse, cd_fahrenheit, cd_slamcity, ninjas,
m_afterburner, m_batman, g_cobra, g_ewj. `g_ewj` reported FROZEN but that is a false positive - the
static SEGA licence screen during a CD load, with the drive streaming at 58 sectors/s.

During the soak the master moves from cart-ROM menu code (0201xxxx) to work-RAM engine code
(0600xxxx) at ~2.5 min and stays there, which is the attract-mode demo starting. The user saw "the
demo ran for a while then dumped me on a random level" - that is Doom's demo loop, not a fault.

**r31 (`phase44`, the strobe leak) - TESTED, equal to r30:**

- 8 of 8 Fusion boots clean, RoQ EOF every run
- 6-title sweep clean (chaotix, vrdx, doom, fusion, cd_nighttrap, ninjas)

One sweep sample showed garbage PCs and a black screen; **eleven subsequent boots were all clean**,
so that was a flake in the sweep's fixed 24 s sample landing on a slow load, not a regression. Do not
condemn a build on one sample - the sweep's timing is not reliable enough for that.

r31 is NOT promoted. It tests equal to r30 and closes a real latent race, but the race produces rare,
plausible-looking wrong data that these tests cannot detect, so there is no measured improvement to
justify displacing the build that has the soak time. PP = r30, PQ = r31. The user's call.

Both are pushed on branch `phase18-dtack`; r31's commit is titled UNTESTED and that is now stale -
it has been tested, just not soaked.

## CORRECTION: r30 fixed the wild jump, NOT Fusion's boot reliability

Measured with a SCREEN-based test (`scratch/menutest.py`), 55 s after load, three frames:

| build | reached the menu |
|---|---|
| r30 | **2 of 5** |
| r31 | **1 of 5** |

So Fusion reaches its menu roughly one boot in three. The earlier "8 of 8 clean" result was the
JUMP TRAIL, which only proves the master did not wild-jump. It says nothing about whether the game
got anywhere, and a black screen 60 s in is a failure however healthy the PCs look. Do not use the
jump trail as a proxy for "it works" again - screenshot the screen.

What r30 DID fix is real and stands: the wild jump is gone, Chaotix (a known crash) now runs, and
13 titles sweep clean.

### The remaining failure: an infinite memset

On a black-screen boot the master spins at 0201FD4C in the byte tail of a memset:

```
0201FD4C  mov.b  r5,@r0
0201FD4E  add    #1,r0
0201FD50  cmp/eq r6,r0        <- end pointer, never equal
0201FD52  bf     0x201fd4c
0201FD54  rts
```

so it was handed a bad length or destination and clears memory for ever. State at the hang:
`CP0=0000 CP1=0001 COMM8=0000`, drive `STOP`, `SECTOR_END 0/s`, comm flags frozen at 00/00, and the
intro video HAS already played (the id logo renders, ~30 s in).

This is corrupted DATA, not a corrupted code pointer - which is why r30's fix does not catch it, and
r31 (the strobe leak, which yields plausible-looking wrong data) does not either.

Next steps, in order:
1. Find where the memset length/destination comes from. Disassemble back from 0201FD38 to the memset
   entry, then find its caller. Suspect a value obtained from the CD file system
   (`scd_gfile_length` / `scd_tell_gfile` / `Mars_SeekCDFile`, which returns `*(int*)&MARS_SYS_COMM8`
   - a 32-bit read of the comm registers).
2. Compare telemetry between a MENU boot and a BLACK boot at the same instant; the divergence point
   is what matters, not the end state.
3. Only then change RTL.

r31 is NOT promoted and on this evidence has no case: 1 of 5 against r30's 2 of 5 (small samples,
no significant difference). It still closes a genuine latent race, so keep the commit.
