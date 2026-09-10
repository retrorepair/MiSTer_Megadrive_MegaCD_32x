#!/bin/bash
# Load a title and decide objectively whether it is running or frozen.
#   tools/mister/freezetest.sh <mgl-basename> <outdir> <label> [settle-seconds]
# Takes three screenshots several seconds apart. Identical PNGs mean the display is not changing,
# which for an animated title (attract loops, scrolling intros) means it has hung. Also reads the
# telemetry sequence, which keeps moving even when the CPUs are dead, so a moving seq with frozen
# frames says the fabric is alive and the cores are not.
set -e
cd "$(dirname "$0")/../.."
MGL="${1:?mgl basename}"; OUT="${2:?outdir}"; LABEL="${3:?label}"; SETTLE="${4:-40}"
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"; PSCP="/c/Program Files/PuTTY/pscp.exe"
sh_() { "$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "$1" 2>/dev/null; }
mkdir -p "$OUT"
sh_ "rm -f /media/fat/screenshots/fz_*.png" >/dev/null
sh_ "echo load_core /media/fat/_Console/${MGL}.mgl > /dev/MiSTer_cmd; sleep ${SETTLE}
for i in 1 2 3; do echo \"screenshot fz_\$i.png\" > /dev/MiSTer_cmd; sleep 4; done" >/dev/null
S1=$(sh_ "python3 /media/fat/hpsmem.py read 30200000 8 | tr -d ' \n'")
sleep 2
S2=$(sh_ "python3 /media/fat/hpsmem.py read 30200000 8 | tr -d ' \n'")
"$PSCP" -batch -hostkey "$HK" -pw 1 "root@$MISTER:/media/fat/screenshots/fz_*.png" "$OUT/" >/dev/null 2>&1
for i in 1 2 3; do mv -f "$OUT/fz_$i.png" "$OUT/${LABEL}_$i.png" 2>/dev/null || true; done
N=$(md5sum "$OUT/${LABEL}"_*.png | awk '{print $1}' | sort -u | wc -l)
if [ "$N" -eq 1 ]; then V="FROZEN (3 identical frames)"; else V="running ($N distinct frames)"; fi
echo "$LABEL: $V   telemetry $S1 -> $S2"
