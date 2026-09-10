#!/bin/bash
# Leave one title running and check every 30 s that it is still alive, screenshotting as it goes.
#   tools/mister/soak.sh <core-basename> <mgl-suffix> <minutes> <outdir>
set -e
cd "$(dirname "$0")/../.."
CORE="$1"; T="$2"; MIN="${3:-10}"; OUT="${4:-soak}"
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"; PSCP="/c/Program Files/PuTTY/pscp.exe"
sh_() { "$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "$1" 2>/dev/null; }
mkdir -p "$OUT"; rm -f "$OUT"/*.png
sh_ "rm -f /media/fat/screenshots/soak_*.png; echo load_core /media/fat/_Console/${CORE}_${T}.mgl > /dev/MiSTer_cmd" >/dev/null
prev=""
for i in $(seq 1 $((MIN*2))); do
	sleep 30
	a=$(sh_ "python3 /media/fat/hpsmem.py read 30200000 8 | tr -d ' \n'")
	sh_ "echo 'screenshot soak_$i.png' > /dev/MiSTer_cmd" >/dev/null
	if [ "$a" = "$prev" ]; then echo "$((i*30))s  $a  *** FROZEN ***"; else echo "$((i*30))s  $a"; fi
	prev="$a"
done
"$PSCP" -batch -hostkey "$HK" -pw 1 "root@$MISTER:/media/fat/screenshots/soak_*.png" "$OUT/" >/dev/null 2>&1 || true
echo "distinct frames:"; md5sum "$OUT"/*.png | awk '{print $1}' | sort -u | wc -l
