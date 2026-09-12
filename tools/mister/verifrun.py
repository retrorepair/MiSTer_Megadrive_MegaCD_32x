#!/usr/bin/env python3
"""Run mcd-verificator on a given core and screenshot the result page.

Same rule as boottest.py: prove the core actually reloaded before timing anything, and fail loudly
if the MGL is missing. Screenshots at several times because the run length is not fixed.

Usage: verifrun.py <tag> <core-suffix>   e.g. verifrun.py base PQ
"""
import os, subprocess, sys, time

tag, prefix = sys.argv[1], sys.argv[2]
MGL = "/media/fat/_Console/MegaCD_%s_verif.mgl" % prefix
if not os.path.exists(MGL): sys.exit("no such MGL: " + MGL)

def cmd(s): os.system("echo \"%s\" > /dev/MiSTer_cmd" % s)
def pid():
    o = subprocess.check_output("ps | grep 'fat/MiSTer ' | grep -v grep || true", shell=True).decode().strip()
    return o.split()[0] if o else None

os.system("rm -f /media/fat/screenshots/%s_*.png" % tag)
was = pid(); now = was
for _ in range(6):
    cmd("load_core " + MGL); t = time.time()
    while time.time() - t < 8:
        time.sleep(0.2); now = pid()
        if now and now != was: break
    if now and now != was: break
if not now or now == was: sys.exit("NO RELOAD")
print("reloaded %s -> %s" % (was, now)); sys.stdout.flush()

for n, wait in ((1, 60), (2, 60), (3, 60), (4, 60)):
    time.sleep(wait)
    cmd("screenshot %s_%d.png" % (tag, n)); time.sleep(4)
    p = "/media/fat/screenshots/%s_%d.png" % (tag, n)
    try: sz = os.path.getsize(p)
    except Exception: sz = 0
    print("t=%ds  %s  %d bytes" % (sum([60]*n), p, sz)); sys.stdout.flush()
