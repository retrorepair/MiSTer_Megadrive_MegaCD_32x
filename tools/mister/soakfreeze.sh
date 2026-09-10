#!/bin/bash
# Load a title and watch for a freeze over minutes, not seconds.
#   tools/mister/soakfreeze.sh <mgl-basename> <outdir> <label> <samples> [gap-seconds]
# A short freeze test cannot catch a fault that only appears after the title has been running for a
# while - Knuckles' Chaotix survived three back-to-back 52 s tests and had still hung by the time it
# was looked at again. Screenshots every <gap> seconds; the run is FROZEN from the first sample whose
# PNG is identical to its predecessor and stays identical to the end.
set -e
cd "$(dirname "$0")/../.."
MGL="${1:?mgl basename}"; OUT="${2:?outdir}"; LABEL="${3:?label}"; N="${4:-12}"; GAP="${5:-25}"
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"; PSCP="/c/Program Files/PuTTY/pscp.exe"
sh_() { "$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "$1" 2>/dev/null; }
mkdir -p "$OUT"; rm -f "$OUT/${LABEL}"_*.png
sh_ "rm -f /media/fat/screenshots/sk_*.png; echo load_core /media/fat/_Console/${MGL}.mgl > /dev/MiSTer_cmd" >/dev/null
echo "$LABEL: loaded, sampling ${N}x every ${GAP}s (~$((N*GAP/60)) min)"
for i in $(seq 1 "$N"); do
	sleep "$GAP"
	# telemetry seq alongside each frame: it keeps moving even when the CPUs are wedged, so a still
	# frame with a moving seq means the cores died and the fabric did not.
	T=$(sh_ "python3 /media/fat/hpsmem.py read 30200000 8 | tr -d ' \n'")
	sh_ "echo 'screenshot sk_$(printf %02d $i).png' > /dev/MiSTer_cmd" >/dev/null
	echo "  sample $i  tel=$T"
done
sleep 3
"$PSCP" -batch -hostkey "$HK" -pw 1 "root@$MISTER:/media/fat/screenshots/sk_*.png" "$OUT/" >/dev/null 2>&1
for f in "$OUT"/sk_*.png; do [ -e "$f" ] && mv -f "$f" "$OUT/${LABEL}_$(basename "$f" .png | tr -d 'sk_')".png; done
echo "  frame md5 sequence:"
md5sum "$OUT/${LABEL}"_*.png | awk '{print "   ", NR, $1}'
U=$(md5sum "$OUT/${LABEL}"_*.png | awk '{print $1}' | sort -u | wc -l)
LASTDUP=$(md5sum "$OUT/${LABEL}"_*.png | awk '{if($1==p)c++; else c=0; p=$1; if(c>=1&&s==0)s=NR} END{print s+0}')
echo "  $U distinct frames of $N; first repeat at sample ${LASTDUP:-none}"
