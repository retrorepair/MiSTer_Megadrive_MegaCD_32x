#!/usr/bin/env python3
"""List which OSD status bits the CONF_STR claims, and which are free.

MiSTer encodes a status bit as a character: '0'-'9' = 0-9, 'A'-'V' = 10-31. Upper-case O uses the
low word, lower-case o the high word (+32); a two-character field like "O67" or "oJM" is a RANGE.
R/D/H prefixes claim bits the same way. The bracket form "O[26]" gives the number directly.

Guessing a "free" bit by eye has now gone wrong twice in one session - bit 27 is CD Audio ("P1OR")
and bit 26 is Enable CDDA ("H2OQ") - so compute it.

  tools/py.sh tools/conf_bits.py core/MegaCD.sv
"""
import re
import sys

src = open(sys.argv[1], encoding="utf-8", errors="replace").read()
m = re.search(r"localparam CONF_STR = \{(.*?)\n\};", src, re.S)
conf = m.group(1) if m else src

used = {}


def val(ch):
    if ch.isdigit():
        return int(ch)
    if "A" <= ch.upper() <= "V":
        return ord(ch.upper()) - ord("A") + 10
    return None


for line in conf.splitlines():
    s = line.strip()
    if not s.startswith('"'):
        continue
    body = s.split('"')[1]
    label = body.split(",")[1] if "," in body else body
    # Strip the page / hide / disable prefixes (P1, D4, H2, h6, d9) or their trailing digit is
    # mistaken for part of the bit field and the lookbehind below rejects the real one.
    while re.match(r"^[PpDdHh][0-9]", body):
        body = body[2:]
    # bracket form: O[26] / R[1] / o[59]
    for mm in re.finditer(r"[ORDH]\[(\d+)\]", body):
        used.setdefault(int(mm.group(1)), label)
    # letter form: O67, oJM, R0, D0 ...  (skip the page/hide prefixes P1 D4 H2 h6 d9)
    for mm in re.finditer(r"(?<![A-Za-z0-9])([ORDHo])([0-9A-Va-v]{1,2})(?=[,;])", body):
        kind, chars = mm.group(1), mm.group(2)
        base = 32 if kind == "o" else 0
        nums = [val(c) for c in chars]
        if any(n is None for n in nums):
            continue
        for n in range(min(nums), max(nums) + 1):
            used.setdefault(n + base, label)
    for mm in re.finditer(r"(?<![A-Za-z0-9])o([0-9A-Va-v]{1,2})(?=[,;])", body):
        nums = [val(c) for c in mm.group(1)]
        if any(n is None for n in nums):
            continue
        for n in range(min(nums), max(nums) + 1):
            used.setdefault(n + 32, label)

# bits referenced in RTL but with no menu entry still count as taken
for mm in re.finditer(r"status\[(\d+)\]", src):
    used.setdefault(int(mm.group(1)), "(RTL only, no CONF_STR entry)")

print("claimed:")
for b in sorted(used):
    print("  %2d  %s" % (b, used[b][:60]))
free = [b for b in range(64) if b not in used]
print("\nFREE:", free)
