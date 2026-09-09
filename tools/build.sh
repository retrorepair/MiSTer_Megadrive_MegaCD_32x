#!/bin/bash
# Detached Quartus 17.0 build: tools/build.sh <project_dir> <project_name> <logfile>
# Runs quartus_sh --flow compile fully detached (survives the caller), log to <logfile>.
DIR="$(cygpath -w "$1")"; PROJ="$2"; LOG="$(cygpath -w "$3")"
powershell.exe -NoProfile -Command "Start-Process -FilePath 'C:\intelFPGA_lite\17.0\quartus\bin64\quartus_sh.exe' -ArgumentList '--flow','compile','$PROJ' -WorkingDirectory '$DIR' -RedirectStandardOutput '$LOG' -RedirectStandardError '${LOG}.err' -WindowStyle Hidden"
echo "launched $PROJ in $DIR -> $LOG"
