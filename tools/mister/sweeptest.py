#!/usr/bin/env python3
"""Load each test title in turn and report whether it is actually running - and prove each load.

Same health readout as the old scratch/sweep30.py:
  MPC/SPC   SH-2 program counters (32X titles)
  JUMP      did the master leave real code for the BIOS region? (the r30 bug's signature)
  MDcyc/s   68000 bus cycles per second - 0 means the Mega Drive is dead
  SEC/s     CDC sectors per second (CD titles; hardware is 75)
  FRAMES    two screenshots 3 s apart: 2 = the picture is changing, 1 = frozen

What is new is that it refuses to guess. MiSTer silently ignores a load_core naming a file that does
not exist, so a harness that trusts the command reports the PREVIOUS title's telemetry under the next
title's name. Every MGL is checked before the run and every load waits for MiSTer's pid to change.

Usage: sweeptest.py <tag> <full-core-name> <title> [title ...]
       e.g. sweeptest.py sw MegaCD_PS chaotix vrdx doom cd_nighttrap
"""
import hashlib, mmap, os, struct, subprocess, sys, time

B = 0x30200000
f = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
m = mmap.mmap(f, 0x10000, mmap.MAP_SHARED, mmap.PROT_READ, offset=B & ~0xFFF)
bs = B & 0xFFF
def beat(o): return struct.unpack_from("<Q", m, bs + o)[0]
def cmd(s): os.system("echo \"%s\" > /dev/MiSTer_cmd" % s)
def pid():
    o = subprocess.check_output("ps | grep 'fat/MiSTer ' | grep -v grep || true", shell=True).decode().strip()
    return o.split()[0] if o else None

tag, core, titles = sys.argv[1], sys.argv[2], sys.argv[3:]
mgls = {t: "/media/fat/_Console/%s_%s.mgl" % (core, t) for t in titles}
missing = [t for t in titles if not os.path.exists(mgls[t])]
if missing:
    sys.exit("no MGL for: " + ", ".join("%s (%s)" % (t, mgls[t]) for t in missing))

os.system("rm -f /media/fat/screenshots/%s_*.png" % tag)
print("%-14s %-9s %-9s %-22s %8s %6s %s" % ("title", "MPC", "SPC", "JUMP", "MDcyc/s", "SEC/s", "FRAMES"))

for t in titles:
    was = pid(); now = was
    for _ in range(6):
        cmd("load_core " + mgls[t]); t0 = time.time()
        while time.time() - t0 < 8:
            time.sleep(0.2); now = pid()
            if now and now != was: break
        if now and now != was: break
    if not now or now == was:
        print("%-14s NO RELOAD" % t); sys.stdout.flush(); continue

    time.sleep(24)
    md0, sec0, t0 = beat(0x28) >> 32, beat(0x18) >> 48, time.time()
    cmd("screenshot %s_%s_a.png" % (tag, t))
    time.sleep(3.0)
    cmd("screenshot %s_%s_b.png" % (tag, t))
    time.sleep(1.0)
    dt = time.time() - t0
    md1, sec1 = beat(0x28) >> 32, beat(0x18) >> 48
    pc, tr = beat(0x20), beat(0x40)
    shots = []
    for s in "ab":
        p = "/media/fat/screenshots/%s_%s_%s.png" % (tag, t, s)
        try: shots.append(hashlib.md5(open(p, "rb").read()).hexdigest())
        except Exception: shots.append(None)
    frames = len(set(x for x in shots if x))
    jump = "clean" if not tr else "*** %08X -> %08X" % (tr >> 32, tr & 0xFFFFFFFF)
    print("%-14s %08X  %08X  %-22s %8d %6.1f %s"
          % (t, pc >> 32, pc & 0xFFFFFFFF, jump,
             int(((md1 - md0) & 0xFFFFFFFF) / dt), ((sec1 - sec0) & 0xFFFF) / dt,
             "%d %s" % (frames, "ok" if frames == 2 else "FROZEN" if frames == 1 else "no shot")))
    sys.stdout.flush()
