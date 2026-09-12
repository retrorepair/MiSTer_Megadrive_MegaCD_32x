#!/usr/bin/env python3
"""Capture the 32X frame buffer and the screen at the same instant.

WHY
Night Trap's intro is displayed shoved a long way left, with black on the right and a sliver of the
left edge reappearing on the right. Every theory so far has been about which side of the 32X bitmap
path is at fault, and screenshots alone cannot separate them. This does, without a rebuild: it takes
a MiSTer screenshot and, in the same breath, copies both 32X frame buffers straight out of the DDR3
the FPGA and the HPS share. Rendering the dump offline says what the MD actually put in memory; the
screenshot says what the display made of it. If the dump is framed correctly and the screen is not,
the fault is on the display side and nowhere else.

FB0 is at HPS 0x30100000 and FB1 at 0x30120000, 128 KB each (see tools/mister/fbdump.py). Telemetry
beat 12 carries MODE in bits [5:4] and the frame-select bits, so each capture records which buffer
was being displayed and in which bitmap mode.

Usage: ntshot.py <mgl-name> <count> [warmup-secs] [gap-secs]
       ntshot.py running <count> [warmup] [gap]     # do not reload, capture what is on screen now
"""
import mmap, os, struct, subprocess, sys, time

mgl, n = sys.argv[1], int(sys.argv[2])
warm = float(sys.argv[3]) if len(sys.argv) > 3 else 25.0
gap = float(sys.argv[4]) if len(sys.argv) > 4 else 2.0

SHOTDIR = "/media/fat/screenshots/MegaCD"
OUT = "/tmp/ntshot"
os.system("rm -rf %s; mkdir -p %s" % (OUT, OUT))


def mister_pid():
    o = subprocess.check_output("ps | grep 'fat/MiSTer ' | grep -v grep || true", shell=True).decode().strip()
    return o.split()[0] if o else None


if mgl != "running":
    path = "/media/fat/_Console/%s.mgl" % mgl
    if not os.path.exists(path):
        sys.exit("no such MGL: " + path)          # MiSTer ignores load_core for a missing file, silently
    was = mister_pid()
    now = was
    for _ in range(6):
        os.system("echo load_core %s > /dev/MiSTer_cmd" % path)
        t = time.time()
        while time.time() - t < 10:
            time.sleep(0.2)
            now = mister_pid()
            if now and now != was:
                break
        if now and now != was:
            break
    if not now or now == was:
        sys.exit("core did not reload")
    print("loaded %s (pid %s -> %s)" % (mgl, was, now), flush=True)
    time.sleep(warm)

fr = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
FB0 = mmap.mmap(fr, 0x20000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30100000)
FB1 = mmap.mmap(fr, 0x20000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30120000)
TEL = mmap.mmap(fr, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30200000)

for i in range(n):
    before = set(os.listdir(SHOTDIR))
    os.system("echo screenshot > /dev/MiSTer_cmd")
    # the dump has to straddle the screenshot: the frame on screen is the one in memory now
    d0 = bytes(FB0[0:0x20000])
    d1 = bytes(FB1[0:0x20000])
    t12 = struct.unpack(">Q", TEL[96:104])[0]
    open("%s/%02d_fb0.bin" % (OUT, i), "wb").write(d0)
    open("%s/%02d_fb1.bin" % (OUT, i), "wb").write(d1)
    shot = ""
    for _ in range(20):
        time.sleep(0.15)
        new = set(os.listdir(SHOTDIR)) - before
        if new:
            shot = sorted(new)[-1]
            break
    if shot:
        d = open("%s/%s" % (SHOTDIR, shot), "rb").read()
        open("%s/%02d_screen.png" % (OUT, i), "wb").write(d)
        os.unlink("%s/%s" % (SHOTDIR, shot))
    print("%02d tel12=%016X shot=%s  fb0 nz=%d fb1 nz=%d"
          % (i, t12, shot or "NONE", 0x20000 - d0.count(0), 0x20000 - d1.count(0)), flush=True)
    time.sleep(gap)

print("done ->", OUT, flush=True)
