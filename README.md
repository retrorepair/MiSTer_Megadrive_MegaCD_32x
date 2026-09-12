# Mega Drive + Mega CD + 32X — one MiSTer core

A single MiSTer FPGA core for the DE10-Nano that is a Mega Drive with **both** of its add-ons attached
at once: the Mega CD on the expansion port and the 32X in the cartridge slot, with a game cartridge
behind the 32X. It runs Mega Drive cartridges, Mega CD discs, 32X cartridges, and CD32X titles that need
the disc drive and the 32X working together.

Existing MiSTer cores give you one add-on or the other. srg320's `MegaCD_MiSTer` is a Mega Drive plus a
Mega CD; his `S32X_MiSTer` is a Mega Drive plus a 32X. Neither can run a CD32X title, because that needs
the Mega CD streaming video into Word RAM while the 32X's two SH-2s blit it to a frame buffer. This
project takes the Mega CD block from one, the 32X and SH-2 blocks from the other, puts them on a single
Mega Drive, and makes the whole thing fit in one Cyclone V.

**Current release:** `releases/MegaCD_MD_MCD_32X_r42_freedec.rbf`. Timing closes with margin, every
tier runs on real hardware, a thirteen-title sweep is clean, and
mcd-verificator now passes 17 of 18. It is not finished — see
[Status](#status) and [Known gaps](#known-gaps) for an honest account of what has and has not been
demonstrated.

---

## Status

Tested on a real DE10-Nano. This table records **what was actually observed**, not what is expected to
work. "Gameplay" means interactive play was reached; anything else says how far it got.

| Tier | Titles run | Furthest observed |
|---|---|---|
| Mega Drive cartridge | Alien 3 | gameplay |
| Mega CD disc | 3 Ninjas Kick Back | **gameplay** |
| Mega CD disc | Cobra Command | full-motion video |
| Mega CD disc | Adventures of Batman & Robin, Earthworm Jim Special Edition | running and animating |
| Mega CD disc | AH-3 Thunderstrike, Bram Stoker's Dracula | title screen |
| Mega CD, no disc | BIOS | boots, logo animation clean |
| 32X cartridge | Knuckles Chaotix | **gameplay** |
| 32X cartridge | Doom | title and menu |
| 32X cartridge | After Burner Complete, Space Harrier, Virtua Racing Deluxe | attract / in-game 3D |
| 32X cartridge | Star Wars Arcade | intro |
| **CD32X** | Night Trap, Corpse Killer, Supreme Warrior | **live full-motion video through the 32X frame buffer** |
| **CD32X** | Slam City with Scottie Pippen | **interactive level-select menu** |
| **CD32X** | Doom CD32X Fusion | **boots to its SELECT GAME menu** |
| **CD32X** | Fahrenheit | running and animating |

All four tiers run. The CD32X tier, the one no other core can do at all, has three titles playing
video and two more reaching an interactive menu — including Doom CD32X Fusion, a mode 1 title that
drives the Mega CD from a cartridge and reads its WAD off the disc while both SH-2s run the game.

"Running and animating" is weaker than the rows above it and means exactly what it says: the sweep
found the 68000 executing, no wild jump on either SH-2, the CD streaming where a disc is involved, and
the picture different between two screenshots three seconds apart. It is not a claim that the title was
played.

Read the sample size honestly: only a handful of titles per tier, and only three have reached extended
gameplay. Titles known NOT to run are listed under [Known gaps](#known-gaps).

**Soak:** ten minutes of Doom CD32X Fusion with no fault; twelve minutes of Night Trap with the
liveness counter advancing at every one of 24 samples and all 24 frames distinct; ten minutes of
3 Ninjas in gameplay with 18 of 20 frames distinct. Night Trap streams at 75.0 sectors/s with a
13.33 ms period, against 13.333 ms on hardware.

**Fit and timing** (release r42, Quartus 17.0.2 Lite, 5CSEBA6U23I7):

| | |
|---|---|
| Logic | 33,453 / 41,910 ALMs (80%) |
| Block RAM | 539 / 553 M10K (97%) |
| DSP | 61 / 112 (54%) |
| worst setup slack | +0.012 ns (`pll_hdmi`, the framework's video scaler) |

Every clock domain has positive setup and hold slack.

Block RAM count is the binding constraint, not logic: 97% of the blocks are in use while only 73% of
the bits inside them are. That single fact drove most of the architecture below.

---

## How the three systems were fitted together

### Bus topology mirrors the hardware

It is two independent grafts onto one Mega Drive, not a three-way bus. The two add-ons never talk to
each other directly — exactly as on a real stack of hardware.

```
                     +----------------+
   expansion port -- |   Mega CD      |   (sub-68000, gate array, CDC, PCM, Word RAM)
                     +----------------+
                              |
                     +----------------+
                     |  Mega Drive    |   68000, Z80, VDP, FM, PSG
                     +----------------+
                              |
   cartridge slot ---+----------------+
                     |     32X        |   two SH-2s, 32X VDP, PWM
                     +----------------+
                              |
                     +----------------+
                     |  game cart     |   ROM, SRAM/EEPROM, mappers
                     +----------------+
```

The Mega Drive drives the 32X with the real cartridge-slot signal set (`VA`, `CE0_N`, `CAS0_N`,
`CAS2_N`, `LWR_N`, `UWR_N`, `ASEL_N`, `CART_N`, plus the `EDCLK`/`VSYNC`/`HSYNC`/`YS_N` genlock lines),
and the Mega CD with the expansion-port set (`ROM_N`, `RAS2_N`, `FDC_N`, `ASEL_N`, and the 68000's own
`/AS`). The game cartridge sits behind the 32X on its pass-through bus. All three devices wire-AND the
shared `/DTACK` exactly as the hardware does.

`/CART` decides the memory map, so mode 1 and mode 2 fall out of the decode rather than being special
cases: with a cartridge present the cart is at `$000000-$3FFFFF`, the Mega CD BIOS at `$400000-$5FFFFF`
and Word RAM at `$600000-$7FFFFF`; without one, the BIOS moves down to `$000000`.

Two details cost real debugging time and are worth knowing about:

- **Read data is selected by address, never by `/DTACK`.** The Mega CD owns exactly its three decoded
  windows; everything else is the cartridge side. Keying the mux off the 32X's `/DTACK` lets a 32X
  acknowledgement outside its own cycle hijack a Mega CD read in flight.
- **The Mega CD gets the 68000's own `/AS`, not the bus arbiter's.** The gate array uses that strobe to
  choose between the fresh Word RAM word and the previously latched one. Feeding it the arbiter's flag,
  which is also asserted for VDP DMA and Z80 cycles, shifts every DMA'd word by one position. That was
  the corrupt band across the Mega CD boot logo.

### Where the memory went

The SDRAM controller has five ports and moves one 16-bit word per ~7 clocks. A bandwidth model
(`phase0/BANDWIDTH.md`) put the CD32X worst case at ~90% of it if everything lived there — a fail. So
the largest 32X memories were moved to the HPS DDR3 instead, which bursts up to 255×64 bits, so a whole
scanline of frame buffer is one ~1 µs request. That drops the SDRAM to ~34%.

| SDRAM port | Contents |
|---|---|
| 0 | game cartridge ROM and SRAM (shared by the MD and both SH-2s through the 32X) |
| 1 | Mega CD BIOS ROM |
| 2 | Mega CD 512 KB PRG-RAM, behind a 512-entry read cache (`rtl/prg_cache.sv`) |
| 3 | Mega CD 64 KB PCM wave RAM |
| 4 | HPS load and save path |

| HPS DDR3 (window at `0x30000000`) | Contents |
|---|---|
| `0x000000` | SH-2 work RAM, 256 KB |
| `0x100000` | 32X frame buffer 0, 128 KB |
| `0x120000` | 32X frame buffer 1, 128 KB |
| `0x200000` | debug telemetry beats (`TELEMETRY` in `s32x_ddr.sv`; on in r38) |

`core/rtl/s32x_ddr.sv` is the one substantial piece of RTL written for this project. It presents the
frame buffers and SH-2 RAM to the 32X as if they were local memory: the display side prefetches a
scanline into a line buffer, the draw side has a write FIFO and a read cache, and the SH-2 side has a
cache-line burst path.

### Clocks

One PLL produces both core clocks: `clk_sys` at 53.693175 MHz (NTSC) and `clk_ram` at exactly twice
that. The SH-2s are stepped by a 3-of-7 enable off `clk_sys`, giving the true **23.011 MHz** — the same
3×VCLK relationship the real 32X uses. srg320's `clk_sys`/2 (26.85 MHz, 17% fast) is still selectable
from the OSD for comparison. The Mega CD's sub-68000, PCM and CDC run at a true 12.5 MHz via a
CEGen-produced 50 MHz enable, rather than upstream's 13.42 MHz which was 7.4% fast.

---

## Accuracy

**Faithful:**

- SH-2s at the real 23.011 MHz, derived as the hardware derives it.
- Mega CD sub-system at a true 12.5 MHz.
- Bus topology, chip-select decode and `/DTACK` wire-AND as on hardware, including mode 1 / mode 2.
- Unmapped addresses in the `$A10000-$A1FFFF` control area terminate their own cycle and return open
  bus, as the console's I/O decoder does. `$A15000-$A15FFF` is deliberately excluded, because the
  console leaves that window unacknowledged so a cartridge can answer it — which is exactly how the 32X
  answers its own registers.
- **CRAM dots** are modelled behind an OSD switch, defaulted off. Writing the palette during active
  display puts the written value on screen for that pixel on real hardware; the VDP this core uses
  had no such path, so the artefact never appeared at all.


**Known deviations, stated up front:**

- **The Mega Drive is fpgagen, not NukedMD.** This was a deliberate choice: fpgagen is far smaller, and
  nothing else would fit alongside both add-ons. The cost is accepted — cycle-exact 68000 behaviour is
  not claimed. It is worth saying that the verificator failures below turned out **not** to be that
  cost: they are SDRAM contention, and the arithmetic is in [Known gaps](#known-gaps).
- **32X frame-buffer read timing.** The real 32X VDP reads the line-table entry at the first active
  pixel and the pixels just in time; here both are read during the preceding HBLANK, about 10 µs early.
  This is a hardware limitation of external memory latency and is commented as such in the RTL. Only
  software racing the beam within a single line could tell.
- **mcd-verificator completes with 1 of 18 tests failing.** See [Known gaps](#known-gaps).

---

## Phase and task checklist

The original roadmap (in `HANDOFF.md` §6) set out six phases with GO/NO-GO gates. Status against it:

### Phase 0 — feasibility by measurement

| Task | Status |
|---|---|
| Build `S32X_MiSTer` as-is, record per-entity resources | **Done** |
| Build `MegaCD_MiSTer` as-is, record per-entity resources | **Done** |
| Sum the parts against the device; GO/NO-GO | **Done** — GO |
| SDRAM bandwidth model for the CD32X worst case | **Done** — `phase0/BANDWIDTH.md`, ~34% with frame buffers on DDR3 |

### Phase 1 — base core (Mega Drive + Mega CD)

| Task | Status |
|---|---|
| Bring up fpgagen + Mega CD on hardware: BIOS, a CD game, a cart | **Done** |
| Port the region-from-BIOS fix | **Done** |
| Port cartridge-slot / `rom_cart_mode` handling | **Done** |
| Port the CEGen 50 MHz enable (true 12.5 MHz Mega CD) | **Done** |
| Port PCM wave RAM into SDRAM | **Done** — saved ~64 M10K |
| Port the CDC `SECTOR_ACTIVE` / frame-timer fixes | **Done** |
| Port the ASIC INT2 acknowledge fix | **Done** |
| Re-run the verificator to get an fpgagen baseline | **Done** — 14 of 18 from r7 to r38, 15 from r39, 16 from r40, 17 from r41 |

### Phase 2 — Mega Drive + 32X

| Task | Status |
|---|---|
| Graft the 32X onto the cartridge bus | **Done** |
| Frame buffers and SH-2 RAM on external memory, line-buffered VDP read | **Done** — `core/rtl/s32x_ddr.sv` |
| The accurate 23.011 MHz SH-2 enable | **Done** |
| Video overlay mixer (32X over MD) | **Done** |
| Milestone: 32X boot ROM → VRDX → Doom → Chaotix | **Done** — all four, Chaotix in gameplay |
| Prove fit and timing with everything present | **Done** — 79% ALMs, 97% M10K, timing closes |

### Phase 3 — Mega CD with the 32X present

| Task | Status |
|---|---|
| Boot the BIOS and a CD game with the 32X instantiated | **Done** |
| `$000000` boot precedence | **Done** |
| Shared reset across three units | **Partial** — MD and Mega CD correct; 32X `VRES_N`/`MRES_N` **stubbed** (tied inactive, as srg320 does) |
| Mega CD PCM/CDDA and 32X PWM coexisting in the mix | **Done** — but see the audio gap below |
| Verificator | **Nearly closed** — 1 of 18 still fails; REG 8030, VAR TESTS and CDC FLAGS closed by the PRG-RAM cache (see Known gaps) |

### Phase 4 — CD32X

| Task | Status |
|---|---|
| Night Trap streaming disc video through the 32X frame buffer | **Done** — live FMV, 12-minute soak |
| Tune SDRAM port priorities and frame-buffer prefetch | **Done** |
| Acceptance: all six CD32X titles boot and play | **Partial** — Night Trap, Corpse Killer and Supreme Warrior play video, Slam City reaches an interactive menu, Fahrenheit runs, Surgical Strike does not boot |
| Doom CD32X Fusion (mode 1: the Mega CD driven from a cartridge) | **Done** — boots to its SELECT GAME menu; ten-minute soak clean |

### Phase 5 — hardening and accuracy

| Task | Status |
|---|---|
| Timing closure | **Done** — +1.353 ns clk_sys; the worst path in the design is in the framework's scaler at +0.383 ns |
| Long soak | **Partial** — longest single runs 12 minutes (Night Trap) and 10 minutes (Fusion); no multi-hour soak |
| DDR3 telemetry technique for live state | **Done** — and it found five of the hard bugs |
| 32X test ROMs (SH-2 timing, PWM) | **Not done** |
| Verificator for the MD/MCD side | **17 of 18 pass** as of r41 — REG 8030 and VAR TESTS fixed by the PRG-RAM port cache; none of these was the fpgagen cost they were assumed to be |
| Audio verified by listening | **Done** — confirmed correct by ear across the tiers heard |
| Backup RAM / SRAM save and load tested | **Not done** |

### Contingencies that turned out not to be needed

The roadmap listed "strip the extras" as a contingency against running out of room. **The design fits
without it**, so it was not done and should not be treated as outstanding work: the HDMI scaler, the
Hq2x line doubler, `video_freak` and the lightgun are all still in the build. Blocks come out only when
something genuinely will not fit, never for tidiness.

What *was* removed, because the design would not otherwise fit: both Game Genie engines and the Cheats
and CRAM-Dots OSD items. `TRANSP_DETECT` (adaptive blend) is constant 0 because the S32X-revision VDP
has no such signal.

---

## Known gaps

Read this before trusting the core with anything important.

- **mcd-verificator completes, with 1 of 18 tests failing** — CDC FLAGS 41. VAR TESTS, IRQ TEST,
  REG 8030 and CDC FLAGS 40 all failed from the start of this project and were written off as the
  price of a behavioural Mega Drive. That was wrong, and they were all one cause: the Mega CD
  sub-CPU was losing time on PRG-RAM that real hardware never loses. Its /AS-to-/DTACK measured
  93 ns at best and 335 ns at worst against a 120 ns deadline, because the main 68000's cartridge
  fetches and the sub-CPU's PRG-RAM reads share one SDRAM controller and because every access waited
  on that controller. Three changes closed it: r39 put a 512-entry read cache on the port
  (`rtl/prg_cache.sv`, ~75% hit rate), r40 made a hit answer in ~37 ns instead of ~93 ns, and r41
  posts writes so the sub-CPU is acknowledged at once — which is what real PRG-RAM does, and what
  the 68000's three-word exception stack push needs when an interrupt has to be serviced inside
  6 NOPs of main-CPU time.

  The pass criteria are disassembled out of the test ROM rather than guessed (`tools/dis68k.py`):
  VAR TESTS wants 23753-23980 (`@0x0189F0`), the IRQ test's last sub-test wants 224-226
  (`@0x018402`, matching jgenesis independently), CDC FLAGS wants `48 <= d4 <= 50` and
  `71 <= d5 <= 73` (`@0x01459A`). Both halves are now known — **d4 = 48, d5 = 70, total 118** — so
  the duty (40.68%) is inside the allowed band and it is the *total* that is ~1.7% short. d4 and d5
  count main↔sub RPC round trips, so what remains is the round trip being slightly slow, not the
  decoder waveform. See `HANDOFF.md`.
  [jgenesis issue 105](https://github.com/jsgroth/jgenesis/issues/105) is the best external
  reference; its author drove the same suite to 18 of 18.
- **Doom CD32X Fusion boots to its SELECT GAME menu**, and a ten-minute soak was clean, but **one boot in four
  ends in a black screen** (3 of 12 on r38, every reload verified; earlier builds were worse).
  The mechanism is known end to end: the game reads `numtextures` from the CD file buffer, which is the
  32X frame buffer at SH-2 `0x24000200`, gets `0xFFFFFFFF` = −1, and calls `memset(ptr, 0, -20)`, which
  zeroes all 256 KB of 32X work RAM including the slave's code. What is *not* known is the last step
  back: a live DDR3 trace of a failing boot shows the buffer taking real CD data, being cleared
  normally, and then **87% of it being filled with 0xFF** in the same instant — so this is a CD read
  that delivered all-ones, not a write that went missing.
- **Surgical Strike did not boot.**
- **A 32X horizontal offset is under investigation.** Night Trap's intro video has been seen sitting
  well to the left, but not reproducibly, and not in every region. Parked.
- **Saves are untested.** Backup RAM and cartridge SRAM/EEPROM save and load paths exist and are wired,
  but no save has been written and read back.
- **The Backup RAM *cartridge* is not modelled.** The "Internal+Cart" OSD option now covers only the
  game cartridge's own SRAM.
- **32X reset lines are stubbed.** `VRES_N` and `MRES_N` are tied inactive.
- **PAL 32X is untested.** Every 32X cartridge requires an NTSC/US console or it stops at its region
  lock. Region is sniffed from the BIOS header, and a MiSTer that auto-loads an EU `boot.rom` comes up
  PAL. What reliably forces US is the core's saved status word: bits 7:6 of
  `/media/fat/config/MegaCD.CFG`, value 2. Note that every core built from this tree shares that one
  file, because MiSTer names it from `CONF_STR` and not from the `.rbf`.
- **A timing debt is recorded in the code.** The cartridge SDRAM port is driven from `cart.sv`'s
  combinational decode; re-registering it broke the boot, so it waits for a later pass. Timing closes
  today because of multicycle exceptions that rest on the SDRAM controller holding `busy` two extra
  cycles, not because the crossing is structurally clean.
- **Main (HPS) support for 32X ROM naming was never done.**

---

## Building

Quartus Prime 17.0.2 Lite, targeting Cyclone V `5CSEBA6U23I7`. A full compile takes 35–60 minutes.

```bash
tools/build.sh core MegaCD core/build.log
```

That launches `quartus_sh --flow compile` fully detached, because a foreground build outlives most
shell timeouts. Two traps are worth knowing:

- The line `Quartus Prime Shell was successful` appears near the *top* of the log — it comes from the
  pre-flow Tcl script, not the compile. The real marker is `Full Compilation was successful`, or simply
  `quartus_sh` exiting.
- Do not judge progress by summing CPU across all `quartus_*` processes. The set changes at every stage
  boundary, so the sum drops and a healthy build looks stalled.

There is no native Python on the development machine; `tools/py.sh` runs scripts under WSL with the
path translation handled.

## Testing on hardware

```bash
tools/deploy.sh core/output_files/MegaCD.rbf MyCore.rbf load
tools/mister/sweep.sh MyCore sweep_out          # load every test title, screenshot, read telemetry
tools/mister/soak.sh  MyCore nighttrap 12 soak  # leave one title running and check it stays alive
```

The core can report its own internal state without a rebuild. When `TELEMETRY` is enabled in
`core/rtl/s32x_ddr.sv`, the core writes counters, audio peaks and bus-probe captures to fixed DDR3
addresses from `0x30200000`, and `tools/mister/hpsmem.py` reads them live from Linux on the MiSTer over
SSH. A frozen sequence number means the core is stuck; the other fields say where. This technique found
the frame-buffer read-ready bug, the SH-2 cache-line burst bug, and the bus lock-up fixed in r3.

`tools/dis68k.py` disassembles 68000 code straight out of a ROM image, so an address caught by a bus
probe can be read as instructions.

**The `phase4`/`phase5`/`phase6` probe scripts produce diagnostic-only builds** that force-terminate bus
cycles nothing acknowledges. Real hardware waits for `/DTACK` indefinitely. Those builds must never be
released; they live on a separate branch. Telemetry itself is harmless and **is compiled into r38**
(`TELEMETRY = 1` in `core/rtl/s32x_ddr.sv`), which is what lets the tools above read a shipping build.

**Verify that a test actually rebooted the core.** A harness that writes `load_core` to
`/dev/MiSTer_cmd` and then screenshots will happily screenshot the *previous* boot: MiSTer silently
ignores a request naming a file that does not exist, and the MGL names are `MegaCD_<tag>_<title>.mgl`,
not `<tag>_<title>.mgl`. Twelve "clean boots" were once one boot photographed twelve times. Check that
MiSTer's pid changes before you start timing, and make the harness fail loudly if the MGL is missing —
`tools/mister/boottest.py` does both.

## Repository layout

| Path | What it is |
|---|---|
| `core/` | the working core — top level is `core/MegaCD.sv` |
| `core/rtl/GEN/` | Mega Drive (fpgagen, from the S32X revision) |
| `core/rtl/MCD/` | Mega CD gate array, sub-CPU, CDC, CDD, PCM |
| `core/rtl/S32X/`, `core/rtl/SH/` | 32X and the SH7604 SH-2s |
| `core/rtl/s32x_ddr.sv` | 32X frame buffers and SH-2 RAM in HPS DDR3 — written for this project |
| `releases/` | shipping bitstreams (not in version control) |
| `phase0/`, `S32X_MiSTer_upstream/`, `32X/`, `SH/` | pristine upstream trees, kept for diffing |
| `tools/` | build, deploy, on-target debug, scripted RTL edits, report parsing |
| `HANDOFF.md` | the running engineering log — read it first |

## Credits and licensing

This core is a merge of other people's work. Almost none of the RTL is original here.

- **srg320** — `MegaCD_MiSTer` (the Mega CD block) and `S32X_MiSTer` plus the `32X` and `SH`
  repositories (the 32X, the SH7604 SH-2s, and the fpgagen revision used). The overwhelming majority of
  this design is his.
- **Gregory Estrade (Torlus)** — the original Genesis/fpgagen core.
- **Sorgelig / Alexey Melnikov** — the MiSTer framework, the fpgagen MiSTer port, the SDRAM and DDR3
  controllers.
- **Jorge Cwik** — FX68K, the cycle-accurate 68000.
- **Jose Tejada (jotego)** — JT12 (YM2612) and JT89 (SN76489).
- **Daniel Wallner** and contributors (MikeJ/fpgaarcade, TobiFlex, Sean Riddle) — the T80 Z80 core.
- **Gregory Hogan (Soltan_G42)** — the audio filters.
- **temlib** — `ascal`, the MiSTer scaler.

Licensing is **mixed**, and no single blanket licence applies. `core/LICENSE` is GPLv3; the top level
and the MiSTer framework carry GPL-2.0-or-later notices; FX68K and JT12/JT89 are GPL-3.0-or-later;
fpgagen's `gen.sv`/`gen_io.sv` and the T80 are under a 3-clause-BSD-style licence; the audio filters are
MIT; `ascal` has its own notice; and the PLL and ROM wrappers are Quartus-generated under Intel's terms.
Note that srg320's `32X`, `SH` and `S32X_MiSTer` trees carry no copyright or licence headers at all, so
his work is credited here on the basis of authorship, not of a licence grant those files state.

`core/rtl/S32X/mdbios.mif` and `shbios.mif` are Sega 32X boot-ROM data inherited from upstream and are
not covered by any of the above.
