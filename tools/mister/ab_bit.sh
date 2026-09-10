#!/bin/bash
# Flip one bit of the core's saved status word and reload, so an OSD debug option can be A/B'd without
# navigating the menu. MiSTer stores the 64-bit status little-endian in the first 8 bytes of the .CFG,
# and names the file from CONF_STR, so every core built from this tree shares MegaCD.CFG.
#   tools/mister/ab_bit.sh <bit> <0|1> [mgl-to-load]
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"
BIT="$1"; VAL="$2"; MGL="$3"
"$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "cd /media/fat/config
[ -f MegaCD.CFG.abbackup ] || cp MegaCD.CFG MegaCD.CFG.abbackup
python3 -c \"
d=bytearray(open('MegaCD.CFG','rb').read()); v=int.from_bytes(d[:8],'little')
b=$BIT
v = (v | (1<<b)) if $VAL else (v & ~(1<<b))
d[:8]=v.to_bytes(8,'little'); open('MegaCD.CFG','wb').write(bytes(d))
print('status %016x  bit %d = %d' % (v,b,($VAL)))\"
sync
${MGL:+echo load_core /media/fat/_Console/$MGL > /dev/MiSTer_cmd}" 2>/dev/null
