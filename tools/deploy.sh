#!/bin/bash
# Copy a built core to the MiSTer and optionally load it.
#   tools/deploy.sh <path/to/core.rbf> <name-on-mister.rbf> [load]
set -e
MISTER=192.168.1.182; PW=1
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"; PSCP="/c/Program Files/PuTTY/pscp.exe"
RBF="$1"; NAME="$2"
[ -f "$RBF" ] || { echo "no $RBF"; exit 1; }
"$PLINK" -ssh -batch -hostkey "$HK" -pw $PW root@$MISTER "true"
"$PSCP" -batch -hostkey "$HK" -pw $PW "$RBF" "root@$MISTER:/media/fat/_Console/$NAME"
"$PLINK" -ssh -batch -hostkey "$HK" -pw $PW root@$MISTER "sync; ls -la /media/fat/_Console/$NAME"
if [ "$3" = "load" ]; then
	"$PLINK" -ssh -batch -hostkey "$HK" -pw $PW root@$MISTER "echo load_core /media/fat/_Console/$NAME > /dev/MiSTer_cmd"
	echo "load_core sent"
fi
