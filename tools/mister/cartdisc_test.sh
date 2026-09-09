#!/bin/bash
# Exercise the four OSD media operations end to end and bring back a screenshot of each step.
#
#   ./cartdisc_test.sh <outdir>
#
# The OSD is invisible to screenshots (MiSTer composites it after the scaler), so the menu is
# driven blind by selection index.  The indices come from Main's menu.cpp: the selection wraps,
# so counting UP from a freshly-opened menu reaches the bottom items regardless of how many
# optional rows are present above them:
#     1 UP = Exit   2 UP = Eject Disc   3 UP = Remove Cartridge & Reset   4 UP = Reset & Eject CD
# A fresh load_core leaves the OSD closed, which is what makes the F12 parity deterministic.
#
# What each step should produce:
#   cart      the cartridge game boots (the Mega CD sits at 400000, /CART low)
#   nocart    after "Remove Cartridge & Reset": the Mega CD BIOS, cartridge slot empty
#   disc      the CD game boots
#   ejected   after "Eject Disc": the drive reports CD_STAT_OPEN with the core still running,
#             and Main logs "MCD: eject" - grep the log, the picture alone is not proof
set -e
cd "$(dirname "$0")/../.."
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"
PSCP="/c/Program Files/PuTTY/pscp.exe"
OUT=${1:-cartdisc}; mkdir -p "$OUT"
sh() { "$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "$1"; }
shot() { sh "sleep ${2:-4}; echo 'screenshot $1.png' > /dev/MiSTer_cmd; sleep 4" >/dev/null; }
load() { sh "echo load_core $1 > /dev/MiSTer_cmd; sleep 10; /media/fat/settle.sh 8 150; sleep 8" >/dev/null; }
keys() { sh "python3 /media/fat/uinput_kbd.py --send $1; sleep 6" >/dev/null; }
mark() { sh "wc -l < /tmp/mister.log"; }

sh "rm -f /media/fat/screenshots/*.png" >/dev/null

echo "== 1. insert cartridge (MGL, index 6) =="
load /media/fat/_Console/MegaCD_cart_test.mgl;      shot cart
echo "== 2. Remove Cartridge & Reset (3 UP) =="
N=$(mark); keys "osd wait:2 up wait:0.5 up wait:0.5 up wait:0.5 enter"; shot nocart 20   # a reset needs ~20 s to reach the BIOS
sh "tail -n +$N /tmp/mister.log | sed 's/\x1b\[[0-9;]*m//g' | grep -iE 'eject|reset|mount' | head -5" || true
echo "== 3. insert disc =="
load /media/fat/_Console/MegaCD_cobra_us.mgl;       shot disc
echo "== 4. Eject Disc (2 UP) =="
N=$(mark); keys "osd wait:2 up wait:0.5 up wait:0.5 enter"; shot ejected
echo "-- log says: --"
sh "tail -n +$N /tmp/mister.log | sed 's/\x1b\[[0-9;]*m//g' | grep -iE 'MCD: eject|eject|mount' | head -5" || true

"$PSCP" -batch -hostkey "$HK" -pw 1 "root@$MISTER:/media/fat/screenshots/*.png" "$OUT/" >/dev/null
ls -la "$OUT"
