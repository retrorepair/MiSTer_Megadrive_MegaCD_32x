#!/usr/bin/env python3
"""Sample both SH-2 program counters repeatedly and report where they are spending their time.

Runs ON the MiSTer. A title that is stuck in a spin-wait shows up as a tight cluster of PCs; a title
that is running normally shows a broad scatter. The clustered address range can then be matched
against the ROM to see exactly what is being polled.

  python3 /media/fat/pcsample.py [samples] [gap-seconds]

Beat 4 at 0x30200020 is {master PC[31:0], slave PC[31:0]} - see tools/phase24_sh2_pc.py.
SH-2 address space: 0x02000000 cart ROM, 0x06000000 SDRAM work RAM, 0x00000000 boot ROM,
0x24000000 frame buffer, 0x20004000 system regs.
"""
import collections
import subprocess
import sys
import time

BASE = 0x30200020
N = int(sys.argv[1]) if len(sys.argv) > 1 else 40
GAP = float(sys.argv[2]) if len(sys.argv) > 2 else 0.25


def region(pc):
    top = pc >> 24
    return {0x00: "bootROM", 0x02: "cartROM", 0x06: "SDRAM", 0x20: "sysreg",
            0x24: "framebuf", 0x22: "fbovr", 0x26: "cram"}.get(top, "%02X??" % top)


m, s = collections.Counter(), collections.Counter()
for _ in range(N):
    out = subprocess.check_output(
        [sys.executable, "/media/fat/hpsmem.py", "read", "%x" % BASE, "8"]).decode().strip()
    v = int.from_bytes(bytes.fromhex(out.split()[-1]), "little")
    m[v >> 32] += 1
    s[v & 0xFFFFFFFF] += 1
    time.sleep(GAP)

for name, c in (("MASTER", m), ("SLAVE", s)):
    print("\n%s SH-2: %d distinct PCs in %d samples" % (name, len(c), N))
    for pc, n in c.most_common(12):
        print("   %08X  %-9s x%d" % (pc, region(pc), n))
    if c:
        lo, hi = min(c), max(c)
        print("   range %08X..%08X (span %d bytes)" % (lo, hi, hi - lo))
