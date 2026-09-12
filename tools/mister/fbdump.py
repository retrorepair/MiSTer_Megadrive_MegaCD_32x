#!/usr/bin/env python3
"""Boot Fusion until it fails, then map exactly which bytes of the frame buffer are 0xFF.

The failing boot writes 0xFF over the frame buffer at a known instant, right after the SH-2 clears
the CD file buffer to zero. If the 0xFF region starts exactly at the buffer base (byte 0x200) and
runs for the length of the lump being read, then what happened is that the SH-2's own word-clear
loop stored ones instead of zeros - a data-path fault, not a lost write. If instead the whole
buffer is 0xFF, something filled it wholesale.

Usage: fbdump.py <tag> <mgl-prefix> <max-boots> [seconds]
"""
import mmap, os, struct, subprocess, sys, time

tag, prefix, nboots = sys.argv[1], sys.argv[2], int(sys.argv[3])
secs = float(sys.argv[4]) if len(sys.argv) > 4 else 45.0
MGL = "/media/fat/_Console/MegaCD_%s_fusion.mgl" % prefix
if not os.path.exists(MGL): sys.exit("no such MGL: " + MGL)

fr = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
FB0 = mmap.mmap(fr, 0x20000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30100000)
FB1 = mmap.mmap(fr, 0x20000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30120000)
WRK = mmap.mmap(fr, 0x40000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30000000)

def cmd(s): os.system("echo \"%s\" > /dev/MiSTer_cmd" % s)
def mister_pid():
    o = subprocess.check_output("ps | grep 'fat/MiSTer ' | grep -v grep || true", shell=True).decode().strip()
    return o.split()[0] if o else None

def runs(d, val):
    """(start, length) of every run of `val` at least 16 bytes long"""
    out = []; i = 0; n = len(d)
    while i < n:
        if d[i] == val:
            j = i
            while j < n and d[j] == val: j += 1
            if j - i >= 16: out.append((i, j - i))
            i = j
        else: i += 1
    return out

for boot in range(1, nboots + 1):
    was = mister_pid(); now = was
    for _ in range(6):
        cmd("load_core " + MGL); t = time.time()
        while time.time() - t < 8:
            time.sleep(0.2); now = mister_pid()
            if now and now != was: break
        if now and now != was: break
    if not now or now == was:
        print("boot %d: NO RELOAD" % boot); sys.stdout.flush(); continue
    time.sleep(secs)
    wk = bytes(WRK[0x8000:0xC000]); nz = 100*(len(wk)-wk.count(0))//len(wk)
    d0 = bytes(FB0[0:0x20000]); ff = 100*d0[0x200:0x4200].count(0xFF)//0x4000
    print("boot %d: wrk_nz=%d%% FF=%d%%" % (boot, nz, ff)); sys.stdout.flush()
    if nz >= 5: continue

    print("\n=== FAILED BOOT: frame buffer 0 map ===")
    r = runs(d0, 0xFF)
    print("0xFF runs >=16 bytes: %d, covering %d of %d bytes" % (len(r), sum(x[1] for x in r), len(d0)))
    for s, l in r[:12]: print("   0x%05X .. 0x%05X  (%d bytes)" % (s, s + l - 1, l))
    if len(r) > 12: print("   ... %d more" % (len(r) - 12))
    z = runs(d0, 0x00)
    print("0x00 runs >=16 bytes: %d, covering %d bytes" % (len(z), sum(x[1] for x in z)))
    for s, l in z[:12]: print("   0x%05X .. 0x%05X  (%d bytes)" % (s, s + l - 1, l))
    print("first 64 bytes at 0x200: " + bytes(d0[0x200:0x240]).hex())
    print("bytes around the end of the first 0xFF run:")
    if r:
        e = r[0][0] + r[0][1]
        print("   0x%05X: %s" % (e - 16, bytes(d0[e-16:e+48]).hex()))
    d1 = bytes(FB1[0:0x20000])
    print("FB1: 0xFF %d%%, 0x00 %d%%" % (100*d1.count(0xFF)//len(d1), 100*d1.count(0)//len(d1)))
    break
