#!/usr/bin/env python3
"""HPS-side reader of the N64 core's memory (runs ON the MiSTer).

The DE10-Nano's 1GB DDR3 is shared: Linux uses the low ~511MB, and the FPGA (the
N64 core: its RDRAM + ROM + framebuffers) uses the top 512MB at HPS physical
0x20000000-0x3FFFFFFF. STRICT_DEVMEM blocks read() on that region but allows the
mmap that this tool uses, so we can read live N64 state from the dev side over SSH
without touching the core.

  hpsmem.py read  <hexaddr> <nbytes>     # dump N bytes (hex)
  hpsmem.py search <hexpattern|@string>  # find a byte pattern in the FPGA window
  hpsmem.py u32   <hexaddr>              # read one little/big-endian word
"""
import sys, mmap, os

FPGA_BASE = 0x20000000
FPGA_SPAN = 0x20000000          # 512 MB
CHUNK     = 0x04000000          # 64 MB map windows

def _fd():
    return os.open("/dev/mem", os.O_RDONLY | os.O_SYNC)

def read(addr, n):
    fd = _fd()
    pa = addr & ~0xFFF
    delta = addr - pa
    length = (n + delta + 0xFFF) & ~0xFFF
    m = mmap.mmap(fd, length, mmap.MAP_SHARED, mmap.PROT_READ, offset=pa)
    data = m[delta:delta + n]
    m.close(); os.close(fd)
    return data

def search(pat, limit=32, start=0, span=FPGA_SPAN):
    fd = _fd(); hits = []; off = start
    end = min(start + span, FPGA_SPAN)
    while off < end and len(hits) < limit:
        sz = min(CHUNK, end - off)
        try:
            m = mmap.mmap(fd, sz, mmap.MAP_SHARED, mmap.PROT_READ, offset=FPGA_BASE + off)
        except Exception as e:
            sys.stderr.write("map fail @0x%08x: %s\n" % (FPGA_BASE + off, e)); off += sz; continue
        i = 0
        while len(hits) < limit:
            j = m.find(pat, i)
            if j < 0:
                break
            hits.append(FPGA_BASE + off + j); i = j + 1
        m.close(); off += sz
    os.close(fd)
    return hits

def main():
    if len(sys.argv) < 2:
        print(__doc__); return 1
    cmd = sys.argv[1]
    if cmd == "read":
        print(read(int(sys.argv[2], 16), int(sys.argv[3])).hex())
    elif cmd == "u32":
        d = read(int(sys.argv[2], 16), 4)
        print("le=0x%08x be=0x%08x" % (int.from_bytes(d, "little"), int.from_bytes(d, "big")))
    elif cmd == "search":
        a = sys.argv[2]
        pat = a[1:].encode() if a.startswith("@") else bytes.fromhex(a)
        start = int(sys.argv[3], 16) - FPGA_BASE if len(sys.argv) > 3 else 0
        span = int(sys.argv[4], 16) if len(sys.argv) > 4 else FPGA_SPAN
        hits = search(pat, start=max(0, start), span=span)
        print("\n".join("0x%08x" % h for h in hits) if hits else "(not found)")
    else:
        print(__doc__); return 1
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
