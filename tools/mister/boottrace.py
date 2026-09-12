#!/usr/bin/env python3
"""Failing vs working Fusion boot, with the CD path in view.

Boot 5 of the poisoned run reproduced the failure and killed the old model with it: the frame-buffer
word does NOT stay unwritten. It is written with real CD data at 30.77 s, cleared at 31.88 s, and then
something fills 87% of the buffer with 0xFF at 31.89 s, which is what the game reads back as
numtextures = -1. So the question is no longer "which write went missing" but "why did this CD read
deliver 0xFF".

This logs the telemetry beats alongside the frame buffer so a failing boot can be compared with a
working one at the same instant:
    COMM0/COMM2/COMM4/COMM8  the 32X <-> 68000 command handshake (beat 6)
    sec_end                  CDC sectors delivered (beat 3), hardware is 75/s
    CFM/CFS                  Mega CD main/sub comm flags (beat 9)
    sub_cyc                  sub-CPU bus cycles (beat 10): is it running at all

Usage: fbwatch6.py <tag> <mgl-prefix> <n-boots> [seconds] [poison]
"""
import mmap, os, struct, subprocess, sys, time

tag, prefix, nboots = sys.argv[1], sys.argv[2], int(sys.argv[3])
secs   = float(sys.argv[4]) if len(sys.argv) > 4 else 50.0
poison = len(sys.argv) > 5 and sys.argv[5] == "1"
MGL = "/media/fat/_Console/MegaCD_%s_fusion.mgl" % prefix
if not os.path.exists(MGL): sys.exit("no such MGL: " + MGL)

fr = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
FB0 = mmap.mmap(fr, 0x20000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30100000)
FB1 = mmap.mmap(fr, 0x20000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30120000)
WRK = mmap.mmap(fr, 0x40000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30000000)
TEL = mmap.mmap(fr, 0x1000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30200000)
if poison:
    fw = os.open("/dev/mem", os.O_RDWR | os.O_SYNC)
    PF = mmap.mmap(fw, 0x40000, mmap.MAP_SHARED, mmap.PROT_WRITE, offset=0x30100000)

def cmd(s): os.system("echo \"%s\" > /dev/MiSTer_cmd" % s)
def mister_pid():
    o = subprocess.check_output("ps | grep 'fat/MiSTer ' | grep -v grep || true", shell=True).decode().strip()
    return o.split()[0] if o else None
def w32(m, off): return struct.unpack("<I", bytes(m[off:off+4]))[0]
def beat(o): return struct.unpack_from("<Q", TEL, o)[0]

res = []
for boot in range(1, nboots + 1):
    os.system("rm -f /media/fat/screenshots/%s_%d.png" % (tag, boot))
    was = mister_pid(); now = was
    for _ in range(6):
        cmd("load_core " + MGL); t_req = time.time()
        while time.time() - t_req < 8:
            time.sleep(0.2); now = mister_pid()
            if now and now != was: break
        if now and now != was: break
    if not now or now == was:
        print("===== boot %d: NO RELOAD =====" % boot); sys.stdout.flush(); continue
    if poison: PF[0:0x40000] = b"\xFF" * 0x40000
    t0 = time.time(); log = []; last = None; nxt = 0.0; sec_prev = None; cyc_prev = None
    while True:
        t = time.time() - t0
        if t > secs: break
        v0, v1 = w32(FB0, 0x200), w32(FB1, 0x200)
        c = beat(0x30)
        key = (v0, v1, c >> 48)
        if key != last:
            log.append("%6.2f FB %08X %08X  COMM0=%04X COMM2=%04X COMM4=%04X COMM8=%04X"
                       % (t, v0, v1, c >> 48, (c >> 32) & 0xFFFF, (c >> 16) & 0xFFFF, c & 0xFFFF))
            last = key
        if t >= nxt:
            nxt = t + 0.25
            d0 = bytes(FB0[0x200:0x4200]); wk = bytes(WRK[0x8000:0xC000])
            sec = beat(0x18) >> 48; cyc = beat(0x50) & 0xFFFF; cd = beat(0x48)
            ds = "" if sec_prev is None else " dSEC=%+d" % (((sec - sec_prev) & 0xFFFF))
            dc = "" if cyc_prev is None else " dCYC=%+d" % (((cyc - cyc_prev) & 0xFFFF))
            sec_prev, cyc_prev = sec, cyc
            log.append("%6.2f  . FF0=%3d%% wrk_nz=%3d%%%s%s CFM=%04X CFS=%04X"
                       % (t, 100*d0.count(0xFF)//len(d0), 100*(len(wk)-wk.count(0))//len(wk),
                          ds, dc, cd >> 48, (cd >> 32) & 0xFFFF))
        time.sleep(0.002)
    wk = bytes(WRK[0x8000:0xC000]); nz = 100*(len(wk)-wk.count(0))//len(wk)
    d0 = bytes(FB0[0x200:0x4200]); ff0 = 100*d0.count(0xFF)//len(d0)
    cmd("screenshot %s_%d.png" % (tag, boot)); time.sleep(4)
    try: sz = os.path.getsize("/media/fat/screenshots/%s_%d.png" % (tag, boot))
    except Exception: sz = 0
    state = "HANG" if nz < 5 else ("BLACK" if sz < 5000 else "OK")
    res.append((boot, state))
    print("===== boot %d: %-5s wrk_nz=%d%% FF0=%d%% png=%d =====" % (boot, state, nz, ff0, sz))
    for l in log: print(l)
    sys.stdout.flush()
print("\nSUMMARY " + " ".join("%d:%s" % r for r in res))
