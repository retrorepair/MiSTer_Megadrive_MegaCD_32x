#!/bin/bash
# Watch the 32X SH-2s for a wedge, using the DDR3 counters rather than screenshots.
#   tools/mister/sh2watch.sh <mgl-basename> <label> <samples> [gap-seconds]
#
# Frames are a poor detector: an attract loop can repeat a frame legitimately, and a still picture
# does not say which block died. Beat 0 of the telemetry carries, per ~2.44 ms:
#     [63:48] magic 5332   [47:32] tel_seq   [31:24] sdr_rd   [23:16] sdr_wr
#     [15:8]  fbd_wr       [7:0]   tel_lp
# sdr_rd / sdr_wr are SH-2 work-RAM requests and fbd_wr is 32X frame-buffer drawing, so all three
# freezing while tel_seq and tel_lp keep moving is exactly "both SH-2s stopped, fabric alive".
# Requires TELEMETRY = 1 in core/rtl/s32x_ddr.sv, so this is meaningless on r7 or any release build.
set -e
cd "$(dirname "$0")/../.."
MGL="${1:?mgl basename}"; LABEL="${2:?label}"; N="${3:-16}"; GAP="${4:-15}"
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"
sh_() { "$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "$1" 2>/dev/null; }
sh_ "echo load_core /media/fat/_Console/${MGL}.mgl > /dev/MiSTer_cmd" >/dev/null
prev=""; dead=0
for i in $(seq 1 "$N"); do
	sleep "$GAP"
	raw=$(sh_ "python3 /media/fat/hpsmem.py read 30200000 8 | tr -d ' \n'")
	# hpsmem prints bytes in memory order; the core writes little-endian, so reverse to get the word.
	w=$(echo "$raw" | sed 's/\(..\)/\1 /g' | tr ' ' '\n' | tac | tr -d '\n')
	seq_=${w:4:4}; sdr_rd=${w:8:2}; sdr_wr=${w:10:2}; fbd=${w:12:2}; lp=${w:14:2}
	cur="$sdr_rd$sdr_wr$fbd"
	tag=""
	if [ -n "$prev" ] && [ "$cur" = "$prev" ]; then tag="  <== SH-2 COUNTERS STATIC"; dead=$((dead+1)); else dead=0; fi
	printf "%s t=%4ds seq=%s sdr_rd=%s sdr_wr=%s fbd_wr=%s lp=%s%s\n" \
	       "$LABEL" "$((i*GAP))" "$seq_" "$sdr_rd" "$sdr_wr" "$fbd" "$lp" "$tag"
	prev="$cur"
	if [ "$dead" -ge 3 ]; then echo "$LABEL: WEDGED at ~$((i*GAP))s (3 consecutive static samples)"; exit 0; fi
done
echo "$LABEL: survived $((N*GAP))s"
