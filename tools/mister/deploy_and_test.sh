#!/bin/bash
# Deploy the current build and run the standard hardware check in one go.
#   ./deploy_and_test.sh <rbf> <outdir> [runs]
# Runs the verificator N times (md5-grouped) and then the four media operations.
set -e
cd "$(dirname "$0")/../.."
RBF=${1:?rbf path}; OUT=${2:?outdir}; N=${3:-12}
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PSCP="/c/Program Files/PuTTY/pscp.exe"
mkdir -p "$OUT"
"$PSCP" -batch -hostkey "$HK" -pw 1 "$RBF" "root@$MISTER:/media/fat/_Console/MegaCD_TEST_NukedMD_20260907.rbf" >/dev/null
echo "deployed $(md5sum "$RBF" | cut -c1-8)"
./tools/mister/verif_loop.sh "$N" "$OUT/verif" | tail -6
./tools/mister/cartdisc_test.sh "$OUT/media" 2>&1 | grep -E '^==|MCD: |Eject image' || true
