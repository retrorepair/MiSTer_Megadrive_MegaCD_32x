#!/bin/bash
# Run mcd-verificator N times and md5-group the result screens.
#   ./verif_loop.sh <N> <outdir> [--f2]
# --f2 presses the core's force-US hotkey after each load; only needed on builds before the
# region fix (f4d1a6c), where the verificator cart's 'W' header re-regioned the machine to PAL.
# Identical result pages give byte-identical PNGs, so grouping by md5 keeps the review cheap.
set -e
cd "$(dirname "$0")/../.."
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"
PSCP="/c/Program Files/PuTTY/pscp.exe"
N=${1:-5}; OUT=${2:-verif_shots}; F2=""
for a in "$@"; do [ "$a" = "--f2" ] && F2="python3 /media/fat/uinput_kbd.py --send f2; sleep 25;"; done
mkdir -p "$OUT"; rm -f "$OUT"/run*.png
sh() { "$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "$1"; }
sh "rm -f /media/fat/screenshots/run*.png" >/dev/null
for i in $(seq 1 "$N"); do
	sh "echo load_core /media/fat/_Console/MegaCD_verif_disc.mgl > /dev/MiSTer_cmd; sleep 10; /media/fat/settle.sh 8 150; sleep 8; $F2 echo 'screenshot run$i.png' > /dev/MiSTer_cmd; sleep 4" >/dev/null
	echo "run $i/$N"
done
"$PSCP" -batch -hostkey "$HK" -pw 1 "root@$MISTER:/media/fat/screenshots/run*.png" "$OUT/" >/dev/null
echo; echo "distinct result pages (count  md5  representative):"
md5sum "$OUT"/run*.png | sort | awk '{c[$1]++; if(!($1 in r)) r[$1]=$2} END {for(k in c) print c[k], k, r[k]}' | sort -rn
