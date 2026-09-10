#!/usr/bin/env python3
"""Disassemble a range of a Mega Drive / Mega CD binary with capstone.

  tools/py.sh tools/dis68k.py <file> <start-hex> <len-hex> [base-hex]

<start> and <len> are FILE offsets; <base> is the address the bytes are executed at (default =
start, so listings read as file offsets). Undecodable words are printed as dc.w and the decoder
resynchronises on the next word, which keeps a listing usable across embedded data tables.
"""
import sys

from capstone import Cs, CS_ARCH_M68K, CS_MODE_M68K_000

path = sys.argv[1]
start = int(sys.argv[2], 16)
length = int(sys.argv[3], 16)
base = int(sys.argv[4], 16) if len(sys.argv) > 4 else start

data = open(path, 'rb').read()[start:start + length]
md = Cs(CS_ARCH_M68K, CS_MODE_M68K_000)

off = 0
while off < len(data):
    chunk = data[off:]
    got = False
    for ins in md.disasm(chunk, base + off, count=1):
        raw = ' '.join('%02X' % b for b in ins.bytes)
        print("%06X  %-20s %-8s %s" % (ins.address, raw, ins.mnemonic, ins.op_str))
        off += ins.size
        got = True
        break
    if not got:
        w = int.from_bytes(data[off:off + 2], 'big')
        print("%06X  %-20s %-8s $%04X" % (base + off, '%02X %02X' % (data[off], data[off + 1]),
                                          'dc.w', w))
        off += 2
