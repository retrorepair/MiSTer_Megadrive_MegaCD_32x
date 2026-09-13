#!/usr/bin/env python3
"""Load a game repeatedly on two cores and time how long each run survives.

WHY
Night Trap freezes during its intro, and single runs of two cores are worthless for deciding which
is worse: both have been seen to freeze today. This loads each core the same number of times under
identical conditions and records, per run, how many seconds of live video it managed before the 32X
frame buffer stopped changing for good. That turns "it crashed again" into a rate.

"Alive" is the frame buffer changing between polls; the run is called dead after DEAD_POLLS
consecutive static polls, and the survival time is when the last change was seen.

Everything it uses lives in /tmp, which is tmpfs, so nothing touches the SD card.

Usage: crashrate.py <runs> <core-a-mgl> <core-b-mgl> [warmup] [watch-secs]"""
import mmap
import os
import struct
import subprocess
import sys
import time

runs = int(sys.argv[1])
mgls = [sys.argv[2], sys.argv[3]]
warm = float(sys.argv[4]) if len(sys.argv) > 4 else 45.0
watch = float(sys.argv[5]) if len(sys.argv) > 5 else 45.0

POLL = 1.5
DEAD_POLLS = 6           # ~9 s of no change before calling it dead

fr = os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)
FB = mmap.mmap(fr, 0x20000, mmap.MAP_SHARED, mmap.PROT_READ, offset=0x30100000)


def pid():
    o = subprocess.check_output("ps | grep 'fat/MiSTer ' | grep -v grep || true", shell=True).decode().strip()
    return o.split()[0] if o else None


def one(mgl):
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
        return None
    time.sleep(warm)

    prev = None
    last_change = None
    static = 0
    t0 = time.time()
    while time.time() - t0 < watch:
        d = bytes(FB[0:0x20000])
        if prev is not None:
            if d != prev:
                last_change = time.time() - t0
                static = 0
            else:
                static += 1
                if static >= DEAD_POLLS and last_change is not None:
                    return last_change
        prev = d
        time.sleep(POLL)
    return watch if last_change is not None else 0.0


for r in range(runs):
    for i, m in enumerate(mgls):
        s = one(m)
        tag = os.path.basename(m)
        if s is None:
            print("run %d %-12s NO RELOAD" % (r, tag), flush=True)
        elif s >= watch:
            print("run %d %-12s survived the whole %.0fs window" % (r, tag, watch), flush=True)
        else:
            print("run %d %-12s died after %.1fs of live video" % (r, tag, s), flush=True)
