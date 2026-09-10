#!/usr/bin/env python3
"""Decode the core's DDR3 telemetry beats, and turn the sector counters into rates.

Runs ON THE MiSTer (python3 is present there). hpsmem.py prints the bytes in memory order and the
core writes 64-bit little-endian, so each beat is reversed before unpacking.

  python3 /media/fat/teldump.py            one sample
  python3 /media/fat/teldump.py 5          two samples 5 s apart, with rates

Beats (BASE 0x30200000, 8 bytes each):
  +0x00  magic 0x5332 | seq | 32X DDR3 counters      (tools/phase2_telemetry.py)
  +0x08  audio peaks | sample-enable count           (tools/phase3_audio_probe.py)
  +0x10  sub-CPU PRG-RAM /AS->/DTACK latency         (tools/phase18_prgram_dtack.py)
  +0x18  SECTOR_END | CDD_SEND | DEC_FRAME | DEC_MID (tools/phase19_sector_rate.py)
"""
import subprocess
import sys
import time

BASE = 0x30200000
HPSMEM = "/media/fat/hpsmem.py"


def beat(off):
    out = subprocess.check_output(
        [sys.executable, HPSMEM, "read", "%x" % (BASE + off), "8"]).decode().strip()
    raw = out.split()[-1]
    return int.from_bytes(bytes.fromhex(raw), "little")


def sample():
    return {"hdr": beat(0x00), "aud": beat(0x08), "bus": beat(0x10), "sec": beat(0x18)}


def show(s):
    h = s["hdr"]
    print("magic %04X  seq %5d   sdr_rd %3d sdr_wr %3d fbd_wr %3d lp %3d"
          % (h >> 48, (h >> 32) & 0xFFFF, (h >> 24) & 0xFF, (h >> 16) & 0xFF,
             (h >> 8) & 0xFF, h & 0xFF))
    if (h >> 48) != 0x5332:
        print("  !! magic wrong - telemetry not running, or the wrong address")

    b = s["bus"]
    # phase20 repacked this beat as {over-threshold[31:0], reads[31:0]}; min/max were dropped once
    # they proved stable at 5 and 15-18 clk_sys. The threshold is OSD bit 27: 0 = >6 (wait states),
    # 1 = >9 (reads early DTACK would corrupt).
    slow, n = b >> 32, b & 0xFFFFFFFF
    print("PRG-RAM reads: n=%d  over-threshold=%d  (%.4f%%)"
          % (n, slow, 100.0 * slow / n if n else 0.0))

    c = s["sec"]
    print("sectors: SECTOR_END %d  CDD_SEND %d  DEC_FRAME %d  DEC_MID %d"
          % (c >> 48, (c >> 32) & 0xFFFF, (c >> 16) & 0xFFFF, c & 0xFFFF))


def main():
    a = sample()
    show(a)
    if len(sys.argv) < 2:
        return
    # Time the interval between the two samples rather than trusting the sleep: each beat() spawns
    # python3 on the ARM, so a four-beat sample adds several hundred ms. Taking dt as the sleep alone
    # inflated CDD_SEND to 85.8/s when it is really 75.
    a = sample()
    ta = time.monotonic()
    time.sleep(float(sys.argv[1]))
    b = sample()
    dt = time.monotonic() - ta
    print("\n--- after %.2f s (measured, not the sleep) ---" % dt)
    show(b)

    def rate(x, y, sh, mask):
        d = (((y >> sh) & mask) - ((x >> sh) & mask)) & mask
        return d / dt

    # The free-running totals include the boot, so the interval delta is the honest figure.
    dn = (b["bus"] & 0xFFFFFFFF) - (a["bus"] & 0xFFFFFFFF)
    ds = (b["bus"] >> 32) - (a["bus"] >> 32)
    if dn:
        print("\nPRG-RAM over this interval: %d reads, %d over threshold (%.4f%%), %.0f reads/s"
              % (dn, ds, 100.0 * ds / dn, dn / dt))

    print("\nrates (hardware is 75/s for all four):")
    print("  SECTOR_END %6.1f/s   CDD_SEND %6.1f/s   DEC_FRAME %6.1f/s   DEC_MID %6.1f/s"
          % (rate(a["sec"], b["sec"], 48, 0xFFFF), rate(a["sec"], b["sec"], 32, 0xFFFF),
             rate(a["sec"], b["sec"], 16, 0xFFFF), rate(a["sec"], b["sec"], 0, 0xFFFF)))
    sec = rate(a["sec"], b["sec"], 48, 0xFFFF)
    if sec > 0:
        print("  sector period %.2f ms  (hardware 13.33 ms)" % (1000.0 / sec))


main()
