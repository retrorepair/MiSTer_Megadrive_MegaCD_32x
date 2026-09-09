# Phase 0 — external-memory bandwidth model (CD32X worst case)

Written 2026-09-09 from the actual controllers in the vendored sources, not from datasheet guesses.

## Controllers as they exist

| Path | Source | Behaviour | Cost |
|---|---|---|---|
| SDRAM (DE10 single 16-bit chip) | `rtl/sdram.sv` (both srg320 cores, same design) | 3 fixed-priority ports, **one 16-bit word per request**, no bursts, no bank interleave, refresh every 766 clocks | IDLE→START→RAS/CAS(2)→CAS(2)+1 = **~7 clocks per word at 107.39 MHz ≈ 15.3 M words/s** (~1.79 M clocks per NTSC frame) |
| DDR3 (HPS f2sdram) | `rtl/ddram.sv` (S32X) | single request port, 4-channel 16-byte line cache; read miss = 2×64-bit beats, write = 1 beat with byte enables; `DDRAM_BURSTCNT` allows up to 255 beats per request | ~100–200 ns latency per request, bandwidth effectively unlimited for our purposes (64-bit @ >100 MHz) |

## Demand per NTSC frame (16.7 ms), all masters saturating at once

| Master | Words/frame (worst) | Notes |
|---|---|---|
| MD 68000 cart ROM (+ work RAM if it stays in SDRAM as in MegaCD_ORIG) | ~32 K | 7.67 MHz / 4 clocks per bus cycle, 100 % bus use |
| MCD sub-68000 PRG-RAM | ~52 K | 12.5 MHz / 4, 100 % bus use (unrealistic; ~60 % typical) |
| MCD PCM sample fetch (RAM in SDRAM per NukedMD project) | ~4.3 K | 8 ch × 32.5 kHz, plus posted writes |
| 32X VDP display read | 36 K (packed) / **72 K (direct colour)** | 320 words × 224 lines, and it is **bursty**: 320 words inside a 63.5 µs active line = 5 M words/s while it runs |
| SH-2 frame-buffer writes (draw) | ~72 K | full-screen blit per frame (CD32X FMV) |
| SH-2 frame-buffer reads | small | rare in FMV, larger in 3D titles (Z-buffer style reads) |
| SH-2 work RAM (256 KB) | large (every cache miss) | **DDR3 in S32X today; keep it there** |

## Verdict

- **Everything on SDRAM:** 232 K words × 7 clocks ≈ 1.62 M of 1.79 M clocks = **~90 %**, and the display read's burst demand alone is 40 % of the controller while a line is active. **FAIL** against the ≤ 70 % gate in the roadmap.
- **Frame buffers + SH-2 work RAM on DDR3, MD/MCD on SDRAM:** SDRAM = 88 K × 7 ≈ 0.62 M clocks = **~34 %**. **PASS** with margin. DDR3 carries the SH-2 RAM (as S32X already does, proven on hardware) plus ~150 K frame-buffer words/frame, which is trivial for the HPS bridge as long as the display read is a per-line burst prefetch rather than word-at-a-time.

## Frame-buffer design that follows

- The 32X VDP (`32X/VDP.sv`) already separates a **display stream** (`FB_DISP_A/Q`, sequential from the line-table start address, one-pixel-clock latency) from a **draw stream** (`FB_DRAW_*`: SH-2/68000 window writes via a 4-entry FIFO, reads with a ~7-clock wait, auto-fill). `FS` picks which physical buffer is which.
- Implement a DDR3 frame-buffer module with: (1) a per-line prefetch — read the line-table entry and then burst the line (≤ 320 words = 80 beats, ~1 µs) into a 1-M10K line buffer during the preceding HBLANK; (2) a draw-side write FIFO with back-pressure into the VDP's existing `ACK_N` wait; (3) draw-side reads through the `ddram` line cache.
- **Accepted deviation (hardware limitation: external memory latency):** the line-table entry and line data are read ~10 µs earlier than the real VDP reads them (during HBLANK instead of at the first active pixel). Only software racing the beam within a single line can observe this. Document it in the core notes.
- The DDR3 path needs a small arbiter in front of `ddram.sv`: channel 0 = SH-2 work RAM, 1 = display prefetch, 2 = draw port.
