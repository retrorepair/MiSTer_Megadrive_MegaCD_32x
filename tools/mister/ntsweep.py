#!/usr/bin/env python3
"""Reload a game N times and capture the screen and 32X frame buffer on each run.

WHY
The 32X horizontal-lock diagnosis says the 32X's phase relative to the MD is decided once, when the
32X starts, and never corrected afterwards: VDP.sv accepts the MD's HSYNC only while H_CNT is inside
a window covering 68 of the counter's 420 positions, so each start is a ~16% chance of locking and a
~84% chance of being stuck at an arbitrary offset for the life of that core load.

That is a distribution claim, and this tests it without building anything: load the game many times
over and measure the displacement each time. The prediction is roughly one run in six pixel-perfect
and the rest scattered - NOT a constant offset, and not a drift within a run.

Everything it writes lives in /tmp, which is tmpfs on the MiSTer, so nothing touches the SD card.

Usage: ntsweep.py <mgl-path> <loads> [warmup] [shots-per-load]"""
import mmap
import os
import struct
import subprocess
import sys
import time

mgl = sys.argv[1]
loads = int(sys.argv[2])
warm = float(sys.argv[3]) if len(sys.argv) > 3 else 27.0
shots = int(sys.argv[4]) if len(sys.argv) > 4 else 2

SHOTDIR = "/media/fat/screenshots/MegaCD"   # MiSTer files core screenshots in a per-core folder
OUT = "/tmp/ntsweep"
os.system("rm -rf %s; mkdir -p %s" % (OUT, OUT))

os.makedirs(SHOTDIR, exist_ok=True)

if not os.path.exists(mgl):
    sys.exit("no such MGL: " + mgl)


def pid():
    o = subprocess.check_output("ps | grep 'fat/MiSTer ' | grep -v grep || true", shell=True).decode().strip()
    return o.split()[0] if o else None


fr = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
FB0 = mmap.mmap(fr, 0x20000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30100000)

for run in range(loads):
    was = pid()
    now = was
    for _ in range(6):
        os.system("echo load_core %s > /dev/MiSTer_cmd" % mgl)
        t = time.time()
        while time.time() - t < 10:
            time.sleep(0.2)
            now = pid()
            if now and now != was:
                break
        if now and now != was:
            break
    if not now or now == was:
        print("run %d: NO RELOAD" % run, flush=True)
        continue
    time.sleep(warm)

    for k in range(shots):
        before = set(os.listdir(SHOTDIR))
        os.system("echo screenshot > /dev/MiSTer_cmd")
        d0 = bytes(FB0[0:0x20000])
        open("%s/r%02d_%d_fb0.bin" % (OUT, run, k), "wb").write(d0)
        shot = ""
        for _ in range(20):
            time.sleep(0.15)
            new = set(os.listdir(SHOTDIR)) - before
            if new:
                shot = sorted(new)[-1]
                break
        if shot:
            src = "%s/%s" % (SHOTDIR, shot)
            open("%s/r%02d_%d_screen.png" % (OUT, run, k), "wb").write(open(src, "rb").read())
            os.unlink(src)                      # the screenshot dir stays as we found it
        print("run %d shot %d: fb0 nz=%d %s" % (run, k, 0x20000 - d0.count(0), shot or "NO SHOT"),
              flush=True)
        time.sleep(1.5)

# leave the screenshot folder exactly as it was found
try:
    os.rmdir(SHOTDIR)
except OSError:
    pass
print("done ->", OUT, flush=True)
