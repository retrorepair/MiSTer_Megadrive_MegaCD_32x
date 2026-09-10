#!/bin/bash
# Read and decode the bus-stall telemetry from a running core.
#   tools/mister/stallinfo.sh
# Beats are written by rtl/s32x_ddr.sv; the layout is documented in tools/phase5_bushang2.py.
MISTER=192.168.1.182
HK="SHA256:FqNJOsj3FLUoMQxgn+cqGoXvVfENmVK4QFoSCMKl2lU"
PLINK="/c/Program Files/PuTTY/plink.exe"
"$PLINK" -ssh -batch -hostkey "$HK" -pw 1 root@$MISTER "python3 - <<'EOF'
import subprocess
def beat(a):
    o=subprocess.check_output(['python3','/media/fat/hpsmem.py','read',a,'8']).decode().split()
    return int.from_bytes(bytes(int(x,16) for x in o),'little')
STATE={0:'IDLE',10:'FDC_READ',12:'NOT_USED'}
SRC={0:'-',1:'68000',2:'Z80',3:'VDP'}
c=beat('30200000'); s=beat('30200010'); h=beat('30200018'); h2=beat('30200020')
print('liveness  magic %04x seq %04x  sh2rd %02x sh2wr %02x fbwr %02x lines %02x'
      % (c>>48, (c>>32)&0xFFFF, (c>>24)&0xFF, (c>>16)&0xFF, (c>>8)&0xFF, c&0xFF))
if (s>>48)!=0x5334:
    print('stall beat magic %04x - not the expected build' % (s>>48)); raise SystemExit
seen=(s>>18)&1
print('stall     magic %04x  seen %d' % (s>>48, seen))
if seen:
    st=(s>>20)&0xF
    print('  latest  \$%06X  %s  state %d (%s)  DTACK_N %d  MEM_RDY %d  by %s  captures %d'
          % ((s>>24)&0xFFFFFF, 'read' if (s>>19)&1 else 'write', st, STATE.get(st,'?'),
             (s>>17)&1, (s>>16)&1, SRC.get((s>>6)&3,'?'), (s>>8)&0xFF))
if (h>>48)==0x5335:
    print('  before  \$%06X then \$%06X' % ((h>>24)&0xFFFFFF, h&0xFFFFFF))
if (h2>>48)==0x5336:
    print('  earlier \$%06X   total give-ups %d' % ((h2>>24)&0xFFFFFF, h2&0xFFFF))
EOF" 2>/dev/null
