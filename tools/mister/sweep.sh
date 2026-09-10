#!/bin/bash
# Load each test title in turn, let it settle, screenshot it, and read the DDR3 telemetry
# (liveness sequence + the bus-stall capture) while it is running.
#   tools/mister/sweep.sh <core-basename> <outdir> [mgl-suffix ...]
# With no suffixes it runs the whole set. Screenshots land in <outdir>.
set -e
cd "$(dirname "$0")/../.."
CORE="${1:-MegaCD_P3}"; OUT="${2:-sweep_shots}"; shift 2 || true
<<<<<<< HEAD
=======
# --f2 presses the core's force-US hotkey after each load. Main auto-loads an EU boot.rom, so the
# console comes up PAL and every 32X title stops at its region-lock screen; the CD tiers do not care.
F2=""
for a in "$@"; do [ "$a" = "--f2" ] && F2="python3 /media/fat/uinput_kbd.py --send f2; sleep 20;"; done
set -- $(for a in "$@"; do [ "$a" = "--f2" ] || echo "$a"; done)
>>>>>>> main
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"; PSCP="/c/Program Files/PuTTY/pscp.exe"
sh_() { "$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "$1" 2>/dev/null; }
TESTS=("$@")
if [ ${#TESTS[@]} -eq 0 ]; then
  TESTS=(usbios cart ninjas m_thunder m_batman g_cobra g_dracula g_ewj doom vrdx chaotix m_afterburner m_spaceharrier m_starwars nighttrap verif)
fi
mkdir -p "$OUT"; rm -f "$OUT"/*.png
sh_ "rm -f /media/fat/screenshots/sw_*.png" >/dev/null
for t in "${TESTS[@]}"; do
  echo "=== $t"
<<<<<<< HEAD
  sh_ "echo load_core /media/fat/_Console/${CORE}_${t}.mgl > /dev/MiSTer_cmd; sleep 12; /media/fat/settle.sh 8 150 || true; sleep 10; echo 'screenshot sw_${t}.png' > /dev/MiSTer_cmd; sleep 4" >/dev/null
=======
  sh_ "echo load_core /media/fat/_Console/${CORE}_${t}.mgl > /dev/MiSTer_cmd; sleep 12; /media/fat/settle.sh 8 150 || true; sleep 10; $F2 echo 'screenshot sw_${t}.png' > /dev/MiSTer_cmd; sleep 4" >/dev/null
>>>>>>> main
  # two telemetry reads a few seconds apart: a moving seq means the core is alive
  a=$(sh_ "python3 /media/fat/hpsmem.py read 30200000 8 | tr -d ' \n'")
  s=$(sh_ "python3 /media/fat/hpsmem.py read 30200010 8 | tr -d ' \n'")
  sleep 3
  b=$(sh_ "python3 /media/fat/hpsmem.py read 30200000 8 | tr -d ' \n'")
  echo "   live: $a -> $b"
  echo "   stall: $s"
done
"$PSCP" -batch -hostkey "$HK" -pw 1 "root@$MISTER:/media/fat/screenshots/sw_*.png" "$OUT/" >/dev/null 2>&1 || true
ls -la "$OUT"
