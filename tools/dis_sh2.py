#!/usr/bin/env python3
"""Disassemble SH-2 code out of a 32X ROM.

  tools/py.sh tools/dis_sh2.py <rom> <sh2-addr-hex> <len-hex>

The SH-2 sees cartridge ROM at 0x02000000, so a PC of 0x0201CBE0 is ROM offset 0x1CBE0. Undecodable
words print as .word and the decoder resynchronises, which keeps listings usable across literal pools
(SH-2 code is full of them, since MOV.L @(disp,PC) is how constants are loaded).
"""
import sys

from capstone import CS_ARCH_SH, CS_MODE_BIG_ENDIAN, CS_MODE_SH2, Cs

ROM_BASE = 0x02000000

path, start, length = sys.argv[1], int(sys.argv[2], 16), int(sys.argv[3], 16)
off = start - ROM_BASE if start >= ROM_BASE else start
data = open(path, 'rb').read()[off:off + length]

md = Cs(CS_ARCH_SH, CS_MODE_SH2 | CS_MODE_BIG_ENDIAN)
md.detail = False

i = 0
while i < len(data):
    done = False
    for ins in md.disasm(data[i:], (off + i) | ROM_BASE, count=1):
        print("%08X  %-12s %-8s %s" % (ins.address,
                                       ' '.join('%02X' % b for b in ins.bytes),
                                       ins.mnemonic, ins.op_str))
        i += ins.size
        done = True
        break
    if not done:
        w = int.from_bytes(data[i:i + 2], 'big')
        print("%08X  %-12s %-8s 0x%04X" % ((off + i) | ROM_BASE,
                                           '%02X %02X' % (data[i], data[i + 1]), ".word", w))
        i += 2
