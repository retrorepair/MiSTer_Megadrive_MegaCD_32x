#!/usr/bin/env python3
"""Hold several keys down at once, then release them.

Runs ON the MiSTer. uinput_kbd.py taps keys one at a time, which cannot reach the core's hidden
debug menu: MegaCD.sv latches `enter` and `esc` separately on key-DOWN and toggles dbg_menu only
while both are held, so the two keys have to overlap.

    python3 /media/fat/kbd_chord.py enter esc        # toggle the core's debug menu

Key names are uinput_kbd.py's.
"""
import sys
import time

sys.path.insert(0, "/media/fat")
from uinput_kbd import EV_KEY, EV_SYN, KEYS, SYN_REPORT, VKbd

names = sys.argv[1:] or ["enter", "esc"]
codes = [KEYS[n] for n in names]

k = VKbd(b"MiSTer chord keyboard")
try:
    for c in codes:
        k._ev(EV_KEY, c, 1)
        k._ev(EV_SYN, SYN_REPORT, 0)
        time.sleep(0.05)
    time.sleep(0.25)
    for c in reversed(codes):
        k._ev(EV_KEY, c, 0)
        k._ev(EV_SYN, SYN_REPORT, 0)
        time.sleep(0.05)
    print("chord sent:", " + ".join(names))
finally:
    k.close()
