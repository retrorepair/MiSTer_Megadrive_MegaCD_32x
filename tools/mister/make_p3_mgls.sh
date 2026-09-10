#!/bin/bash
# Clone the P2G test MGLs onto a new core name, and add the verificator combination
# (a disc in the CD slot plus the verificator cartridge, which is how it is meant to run).
#   tools/mister/make_p3_mgls.sh <core-basename>     e.g. MegaCD_P3
set -e
CORE="${1:-MegaCD_P3}"
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"
"$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "
cd /media/fat/_Console
for f in MegaCD_P2G_*.mgl m_*.mgl g_*.mgl; do
  case \"\$f\" in MegaCD_P2G_*) n=\"${CORE}_\${f#MegaCD_P2G_}\" ;; *) n=\"${CORE}_\${f}\" ;; esac
  sed 's|_Console/MegaCD_P2G|_Console/${CORE}|' \"\$f\" > \"\$n\"
done
cat > ${CORE}_verif.mgl <<'M'
<mistergamedescription>
<rbf>_Console/${CORE}</rbf>
<file delay=\"2\" type=\"s\" index=\"0\" path=\"/media/fat/cifs/MegaCD/rr-sega-mega-cd/bin/usa/3 Ninjas Kick Back (USA).chd\"/>
<file delay=\"4\" type=\"f\" index=\"6\" path=\"/media/fat/games/MegaCD/mcd-verificator.bin\"/>
</mistergamedescription>
M
cat > ${CORE}_bios.mgl <<'M'
<mistergamedescription>
<rbf>_Console/${CORE}</rbf>
</mistergamedescription>
M
sync; ls ${CORE}*.mgl
"
